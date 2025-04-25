import os
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from time import sleep
from datetime import datetime
from socket import gethostbyname, getfqdn

from PyQt5 import QtCore


class RunEvent(QtCore.QThread):
    """
    WorkerRunEvent runs network discovery tasks asynchronously using QThread.
    It connects to multiple devices, executes show commands based on user selections,
    and aggregates the data for reporting.

    Signals:
        add_progress (float): Signal to update the progress bar in the UI.
    """

    add_progress = QtCore.pyqtSignal(float)

    def __init__(self, form):
        """
        Initialize the background worker.

        Args:
            form (QWidget): Parent form containing UI elements and session data.
        """
        super().__init__()
        self.form = form

    def run(self):
        """
        Entry point for the thread execution.
        Prepares parameters, runs discovery tasks, processes data, and emits progress.
        """
        os.makedirs(self.form.output_dir, exist_ok=True)

        self.devices = list(filter(None, self.form.device_text_edit.toPlainText().splitlines()))
        if not self.devices:
            logging.warning("No devices provided.")
            return

        self.progress_per_device = 90 / len(self.devices)

        # Flags based on UI selections
        self.interface_enabled = self.form.checkboxes["interface"].isChecked()
        self.mac_enabled = self.form.checkboxes["mac"].isChecked()
        self.arp_enabled = self.form.checkboxes["arp"].isChecked()
        self.discovery_enabled = self.form.checkboxes["cdp_lldp"].isChecked()
        self.vlan_enabled = self.form.checkboxes["vlans"].isChecked()
        self.switchport_enabled = self.form.checkboxes["switchport"].isChecked()
        self.ip_interface_enabled = self.form.checkboxes["ip_interface"].isChecked()
        self.routing_enabled = self.form.checkboxes["routing"].isChecked()
        self.inventory_enabled = self.form.checkboxes["inventory"].isChecked()
        self.config_enabled = self.form.checkboxes["config"].isChecked()

        logging.info("RunEvent started.")
        self.data = {'summary': {}, 'links': {}}

        self.thread_executor()
        self.refactor_data()
        self.reporting()

        logging.info("RunEvent finished.")
        self.add_progress.emit(2)

    def thread_executor(self):
        """
        Run network discovery tasks in parallel using a thread pool.
        Logs any exceptions from individual device tasks.
        """
        logging.info("Starting thread pool execution...")
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {}
            for device in self.devices:
                futures[device] = executor.submit(self.netdisc_task, device)
                sleep(0.5)

            executor.shutdown(wait=True)

            for device in self.devices:
                exception = futures[device].exception()
                if exception:
                    logging.error(f"Exception occurred for {device}: {exception}")

    def netdisc_task(self, device):
        """
        Executes a series of discovery commands on a network device and collects parsed data.

        Args:
            device (str): The IP or hostname of the network device.
        """

        def _normalize_iface(iface):
            """
            Normalize abbreviated interface names.

            Args:
                iface (str): Interface name in abbreviated form.

            Returns:
                str: Normalized interface name.
            """
            labels = ['Te', 'Gi', 'Fa', 'Eth', 'Lo', 'Vl', 'Two', 'Twe']
            for label in labels:
                if re.search(f'^{label}', iface, flags=re.IGNORECASE):
                    port_id = re.search(r'(\d+\S*)', iface).group(0)
                    return f'{label}{port_id}'
            return iface

        def _expand_iface(iface):
            """
            Expand abbreviated interface names to full names.

            Args:
                iface (str): Abbreviated interface name.

            Returns:
                str: Expanded interface name.
            """
            labels = {
                'Te': 'TenGigabitEthernet', 'Gi': 'GigabitEthernet', 'Fa': 'FastEthernet',
                'Eth': 'Ethernet', 'Two': 'TwoGigabitEthernet', 'Twe': 'TwentyFiveGigE',
                'Lo': 'Loopback', 'Vl': 'Vlan'
            }
            for short_label, long_label in labels.items():
                if re.search(f'^{short_label}', iface, flags=re.IGNORECASE):
                    port_id = re.search(r'(\d+\S*)', iface).group(0)
                    return f'{long_label}{port_id}'
            return iface

        from netcore import GenericHandler, get_config_section

        logging.info(f'Connecting to {device}...')

        proxy = {
            'hostname': self.form.session['JUMPHOST_IP'],
            'username': self.form.session['JUMPHOST_USERNAME'],
            'password': self.form.session['JUMPHOST_PASSWORD']
        } if self.form.session['JUMPHOST_IP'] else None

        try:
            handler = GenericHandler(
                hostname=device,
                username=self.form.session['NETWORK_USERNAME'],
                password=self.form.session['NETWORK_PASSWORD'],
                proxy=proxy,
                handler='NETMIKO'
            )
            logging.info(f'Connection established to {device}')
        except Exception:
            logging.error(f'Connection failed to {device}')
            self.add_progress.emit(self.progress_per_device)
            return

        logging.info(f'Capturing & parsing show commands for {device}')
        iface_data = handler.sendCommand(cmd='show interface', autoParse=True, key='interface')

        iface_status_data = {}
        iface_desc_data = {}
        if self.interface_enabled:
            logging.info(f'Gathering "show interface status" for {device}')
            iface_status_data = handler.sendCommand(cmd='show interface status', autoParse=True, key='interface')

            logging.info(f'Gathering "show interface description" for {device}')
            iface_desc_data = handler.sendCommand(cmd='show interface description', autoParse=True, key='interface')

        swport_data = {}
        if self.switchport_enabled:
            logging.info(f'Gathering "show interface switchport" for {device}')
            swport_data = handler.sendCommand(cmd='show interface switchport', autoParse=True, key='interface')

        vlan_data = {}
        if self.vlan_enabled:
            logging.info(f'Gathering VLAN information for {device}')
            vlan_data = handler.sendCommand(cmd='show vlan', autoParse=True, key='vlan_id')

        mac_data = {}
        if self.mac_enabled:
            logging.info(f'Gathering "show mac address" for {device}')
            mac_data = handler.sendCommand(cmd='show mac address', autoParse=True, key='mac_address')

        arp_data = {}
        if self.arp_enabled:
            logging.info(f'Gathering "show ip arp" for {device}')
            arp_data = handler.sendCommand(cmd='show ip arp', autoParse=True, key='mac_address')

        lldp_data = {}
        cdp_data = {}
        if self.discovery_enabled:
            logging.info(f'Gathering "show lldp neighbors" for {device}')
            lldp_data = handler.sendCommand(cmd='show lldp neighbors', autoParse=True, key='local_interface')

            logging.info(f'Gathering "show cdp neighbors" for {device}')
            cdp_data = handler.sendCommand(cmd='show cdp neighbors', autoParse=True, key='local_interface')

        ip_iface_data = {}
        if self.ip_interface_enabled:
            logging.info(f'Gathering "show ip interface" for {device}')
            ip_iface_data = handler.sendCommand(cmd='show ip interface', autoParse=True, key='interface')

        bgp_neighbor_data = {}
        ospf_neighbor_data = {}
        if self.routing_enabled:
            logging.info(f'Gathering "show ip bgp neighbors" for {device}')
            bgp_neighbor_data = handler.sendCommand(cmd='show ip bgp neighbors', autoParse=True, key='neighbor')

            logging.info(f'Gathering "show ip ospf interface brief" for {device}')
            ospf_neighbor_data = handler.sendCommand(cmd='show ip ospf interface brief', autoParse=True,
                                                     key='interface')

        config = ''
        if self.config_enabled:
            logging.info(f'Gathering "show runn" for {device}')
            config = handler.sendCommand(cmd='show runn')

        version_data = {}
        mgmt_ip = ''
        if self.inventory_enabled:
            logging.info(f'Gathering "show version" for {device}')
            version_data = handler.sendCommand(cmd='show version', autoParse=True)[0]

            logging.info(f'Finding MGMT IP from hostname for {device}')
            mgmt_ip = gethostbyname(device)

        logging.info(f'Processing output for {device}')
        link_data = {}

        for iface, iface_props in iface_data.items():
            iface = _normalize_iface(iface)
            link_data[iface] = {}

            # Interface Status and Description
            if self.interface_enabled:
                link_data[iface].update({
                    'Status': '', 'Description': '', 'Link': '',
                    'Duplex': '', 'Speed': '', 'MediaType': ''
                })
                for status_iface, status_props in iface_status_data.items():
                    if iface == _normalize_iface(status_iface):
                        link_data[iface]['Status'] = status_props['status']
                        link_data[iface]['Description'] = status_props['name']
                        link_data[iface]['Link'] = status_props['vlan_id']
                        link_data[iface]['Duplex'] = status_props['duplex']
                        link_data[iface]['Speed'] = status_props['speed']
                        link_data[iface]['MediaType'] = status_props['type']
                for desc_iface, desc_props in iface_desc_data.items():
                    if iface == _normalize_iface(desc_iface):
                        link_data[iface]['Description'] = desc_props['description']

            # Switchport Details
            if self.switchport_enabled:
                link_data[iface].update({
                    'Switchport': '', 'Access': '', 'Voice': '',
                    'Trunk': '', 'Native': ''
                })
                for sw_iface, sw_props in swport_data.items():
                    if iface == _normalize_iface(sw_iface):
                        link_data[iface]['Switchport'] = sw_props['mode']
                        link_data[iface]['Access'] = sw_props['access_vlan']
                        link_data[iface]['Voice'] = sw_props['voice_vlan']
                        link_data[iface]['Trunk'] = sw_props['trunking_vlans']
                        link_data[iface]['Native'] = sw_props['native_vlan']

            # VLAN Information
            if self.vlan_enabled:
                link_data[iface]['VlanName'] = ''
                for vlan_id, vlan_props in vlan_data.items():
                    for vlan_iface in vlan_props['interfaces']:
                        if iface == _normalize_iface(vlan_iface):
                            link_data[iface]['VlanName'] = vlan_props['vlan_name']

            # Discovery (LLDP/CDP)
            if self.discovery_enabled:
                link_data[iface].update({
                    'Neighbor': '', 'Platform': '', 'Capability': '', 'RemoteIface': ''
                })
                for lldp_iface, lldp_props in lldp_data.items():
                    if iface == _normalize_iface(lldp_iface):
                        link_data[iface]['Neighbor'] = lldp_props['neighbor']
                        link_data[iface]['Capability'] = lldp_props['capabilities']
                        link_data[iface]['RemoteIface'] = _normalize_iface(lldp_props['remote_interface'])
                for cdp_iface, cdp_props in cdp_data.items():
                    if iface == _normalize_iface(cdp_iface):
                        link_data[iface]['Neighbor'] = cdp_props['neighbor']
                        link_data[iface]['Capability'] = cdp_props['capability']
                        link_data[iface]['Platform'] = cdp_props['platform']
                        link_data[iface]['RemoteIface'] = _normalize_iface(cdp_props['remote_interface'])

            # MAC Address and ARP
            if self.mac_enabled:
                link_data[iface].update({'MAC': [], 'VLAN': []})
                if self.arp_enabled:
                    link_data[iface].update({'ARP': [], 'FQDN': []})
                for mac, mac_props in mac_data.items():
                    if iface == _normalize_iface(mac_props['ports']):
                        link_data[iface]['MAC'].append(mac)
                        link_data[iface]['VLAN'].append(mac_props['vlan_id'])
                        if self.arp_enabled:
                            ip_addr = arp_data.get(mac, {}).get('ip_address', '')
                            fqdn = getfqdn(ip_addr) if ip_addr else ''
                            link_data[iface]['ARP'].append(ip_addr)
                            link_data[iface]['FQDN'].append(fqdn)

            # IP Interface
            if self.ip_interface_enabled:
                link_data[iface].update({'IP Interface': '', 'VRF': ''})
                for ip_iface, ip_props in ip_iface_data.items():
                    if iface == _normalize_iface(ip_iface):
                        if ip_props['ip_address']:
                            link_data[iface]['IP Interface'] = f"{ip_props['ip_address']}/{ip_props['mask']}"
                        link_data[iface]['VRF'] = ip_props['vrf']

            # Routing Protocols
            if self.routing_enabled:
                link_data[iface]['Routing'] = {}
                for nei, nei_props in bgp_neighbor_data.items():
                    if nei_props['localhost_ip'] == iface_props.get('ip_address'):
                        link_data[iface]['Routing']['BGP'] = {
                            'remoteAsn': nei_props['remote_asn'],
                            'state': nei_props['bgp_state']
                        }
                for ospf_iface, ospf_props in ospf_neighbor_data.items():
                    if iface == _normalize_iface(ospf_iface):
                        link_data[iface]['Routing']['OSPF'] = {
                            'area': ospf_props['area'],
                            'state': ospf_props['state']
                        }

            # Configuration
            if self.config_enabled:
                link_data[iface]['Config'] = get_config_section(f'interface {_expand_iface(iface)}', config)

        # Store per-interface data
        self.data['links'][device] = link_data

        # Device summary
        summary_data = {}
        if self.inventory_enabled:
            summary_data.update({
                'Hostname': version_data.get('hostname', ''),
                'Version': version_data.get('version', ''),
                'Model': version_data.get('hardware', ''),
                'SerialNo': version_data.get('serial', ''),
                'Uptime': version_data.get('uptime', ''),
                'IP': mgmt_ip
            })
        self.data['summary'][device] = summary_data

        # Finalize
        logging.info(f'Completed processing for {device}')
        self.add_progress.emit(self.progress_per_device)
        if hasattr(logging, 'savings'):
            logging.savings(120)

    def refactor_data(self):
        """
        Refactor summary and link data into indexed dictionaries.

        This method restructures the 'summary' and 'links' sections of `self.data` by converting
        device-based keys into sequential index-based keys, preserving all associated properties.
        """
        logging.info("Refactoring data structure for reporting")

        summary_idx = 0
        link_idx = 0
        summary_data = {}
        link_data = {}

        for device in self.devices:
            # Refactor summary data
            for summary_device, summary_props in self.data['summary'].items():
                if device == summary_device:
                    summary_idx += 1
                    summary_data[summary_idx] = {'Hostname': device}
                    summary_data[summary_idx].update(summary_props)

            # Refactor link data
            for link_device, link_props in self.data['links'].items():
                if device == link_device:
                    for link, link_detail in link_props.items():
                        link_idx += 1
                        link_data[link_idx] = {'Port': link, 'Hostname': device}
                        for prop, value in link_detail.items():
                            link_data[link_idx][prop] = value if value else ''

        self.data['summary'] = summary_data
        self.data['links'] = link_data

    def reporting(self):
        """
        Generate an Excel report with summary and link data.

        Creates an Excel workbook with 'Summary' and 'Links' worksheets,
        if the corresponding data is available in `self.data`.
        """
        from netcore import XLBW

        # Set the report output path
        timestamp = datetime.now().strftime('%Y-%m-%d_%H.%M')
        filename = f"{os.path.basename(os.path.dirname(__file__)).title()}_{timestamp}.xlsx"
        self.form.output_report = os.path.join(self.form.output_dir, filename)

        if self.data['summary'] or self.data['links']:
            workbook = XLBW(self.form.output_report)

            # Write summary data if available
            if self.data['summary']:
                logging.info("Generating summary worksheet")
                worksheet_summary = workbook.add_worksheet('Summary')
                worksheet_summary.freeze_panes(1, 2)
                workbook.dump(self.data['summary'], worksheet_summary)

            # Write link data if available
            if self.data['links']:
                logging.info("Generating links worksheet")
                worksheet_links = workbook.add_worksheet('Links')
                worksheet_links.freeze_panes(1, 3)
                workbook.dump(self.data['links'], worksheet_links)

            workbook.close()

        self.add_progress.emit(8)
