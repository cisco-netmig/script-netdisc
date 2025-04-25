import logging
import os
from PyQt5 import QtWidgets, QtGui, QtCore
from .workers import RunEvent


class Ui_Form:
    """
    A PyQt5 UI form class for configuring and executing network diagnostics.

    """

    def setup_ui(self, form):
        """
        Set up the layout and UI elements of the diagnostics form.

        Args:
            form (QWidget): The parent widget to apply the layout and components to.
        """
        grid_layout = QtWidgets.QGridLayout(form)

        # Devices input group
        device_group = QtWidgets.QGroupBox("Devices", form)
        device_layout = QtWidgets.QGridLayout(device_group)
        device_layout.setContentsMargins(5, 5, 5, 5)

        self.device_text_edit = QtWidgets.QPlainTextEdit(device_group)
        device_layout.addWidget(self.device_text_edit, 0, 0)

        grid_layout.addWidget(device_group, 0, 0)

        # Right widget and layout
        right_widget = QtWidgets.QWidget(form)
        right_layout = QtWidgets.QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(30)

        # Diagnostics group
        diagnostics_group = QtWidgets.QGroupBox("Diagnostics", right_widget)
        diagnostics_layout = QtWidgets.QGridLayout(diagnostics_group)
        diagnostics_layout.setHorizontalSpacing(20)
        diagnostics_layout.setVerticalSpacing(15)

        self.checkboxes = {
            "mac": QtWidgets.QCheckBox("MAC"),
            "switchport": QtWidgets.QCheckBox("Switchport"),
            "cdp_lldp": QtWidgets.QCheckBox("CDP/LLDP"),
            "ip_interface": QtWidgets.QCheckBox("IP Interface"),
            "arp": QtWidgets.QCheckBox("ARP"),
            "routing": QtWidgets.QCheckBox("Routing"),
            "inventory": QtWidgets.QCheckBox("Inventory"),
            "interface": QtWidgets.QCheckBox("Interface"),
            "config": QtWidgets.QCheckBox("Config"),
            "vlans": QtWidgets.QCheckBox("VLANs"),
        }

        # Enable all checkboxes by default
        for checkbox in self.checkboxes.values():
            checkbox.setChecked(True)

        diagnostics_layout.addWidget(self.checkboxes["interface"], 0, 0)
        diagnostics_layout.addWidget(self.checkboxes["mac"], 0, 1)
        diagnostics_layout.addWidget(self.checkboxes["arp"], 0, 2)
        diagnostics_layout.addWidget(self.checkboxes["cdp_lldp"], 1, 0)
        diagnostics_layout.addWidget(self.checkboxes["vlans"], 1, 1)
        diagnostics_layout.addWidget(self.checkboxes["switchport"], 1, 2)
        diagnostics_layout.addWidget(self.checkboxes["ip_interface"], 2, 0)
        diagnostics_layout.addWidget(self.checkboxes["routing"], 2, 1)
        diagnostics_layout.addWidget(self.checkboxes["inventory"], 3, 0)
        diagnostics_layout.addWidget(self.checkboxes["config"], 3, 1)

        right_layout.addWidget(diagnostics_group)

        # Actions group
        actions_group = QtWidgets.QGroupBox("Actions", right_widget)
        actions_layout = QtWidgets.QGridLayout(actions_group)

        self.run_button = QtWidgets.QPushButton("Run", actions_group)
        self.run_button.setMinimumSize(QtCore.QSize(120, 0))
        self.run_button.setMaximumSize(QtCore.QSize(100, 16777215))
        self.run_button.setIcon(self._get_icon("run-command"))
        self.run_button.setIconSize(QtCore.QSize(20, 20))
        self.run_button.setCheckable(True)

        actions_layout.addWidget(self.run_button, 0, 0)
        actions_layout.addItem(QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding), 0, 1)

        right_layout.addWidget(actions_group)

        # Outputs group
        outputs_group = QtWidgets.QGroupBox("Outputs", right_widget)
        outputs_layout = QtWidgets.QGridLayout(outputs_group)
        outputs_layout.setHorizontalSpacing(50)

        self.reports_button = QtWidgets.QPushButton("Report", outputs_group)
        self.reports_button.setMinimumSize(QtCore.QSize(120, 0))
        self.reports_button.setIcon(self._get_icon("xls"))
        self.reports_button.setIconSize(QtCore.QSize(20, 20))
        self.reports_button.setCheckable(True)

        self.folder_button = QtWidgets.QPushButton("Folder", outputs_group)
        self.folder_button.setMinimumSize(QtCore.QSize(120, 0))
        self.folder_button.setIcon(self._get_icon("opened-folder"))
        self.folder_button.setIconSize(QtCore.QSize(20, 20))
        self.folder_button.setCheckable(True)

        outputs_layout.addWidget(self.reports_button, 0, 1)
        outputs_layout.addWidget(self.folder_button, 1, 1)
        outputs_layout.addItem(QtWidgets.QSpacerItem(86, 20, QtWidgets.QSizePolicy.Expanding), 1, 2)

        right_layout.addWidget(outputs_group)

        # Progress bar
        self.progress_bar = QtWidgets.QProgressBar(right_widget)
        self.progress_bar.setProperty("value", 0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        right_layout.addWidget(self.progress_bar)

        right_layout.addItem(
            QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding))

        grid_layout.addWidget(right_widget, 0, 1)

    def _get_icon(self, filename: str) -> QtGui.QIcon:
        """
        Load an icon from the assets directory.

        Args:
            filename (str): Name of the icon file (without extension).

        Returns:
            QtGui.QIcon: The QIcon object.
        """
        icon_path = os.path.join(os.path.dirname(__file__), "assets", f"{filename}.ico")
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(icon_path), QtGui.QIcon.Mode.Normal, QtGui.QIcon.State.Off)
        return icon


class Form(QtWidgets.QWidget, Ui_Form):
    """
    UI Form class.

    """

    def __init__(self, parent=None, **kwargs):
        """
        Initialize the UI form.

        Args:
            parent (QWidget): Parent widget.
            **kwargs: Additional arguments for customization or metadata.
        """
        super().__init__(parent)
        self.kwargs = kwargs
        self.session = kwargs.get("session")

        self.setup_ui(self)

        self.output_dir = os.path.join(self.kwargs.get("output_dir"),
                                       os.path.basename(os.path.dirname(__file__).upper()))
        self.output_report = ""

        self.run_button.clicked.connect(self.start_run_event)
        self.reports_button.clicked.connect(lambda: self.open_path(self.output_report))
        self.folder_button.clicked.connect(lambda: self.open_path(self.output_dir))

        logging.debug("Diagnostics form initialized.")

    def start_run_event(self):
        """
        Trigger the diagnostics run event. Disables the run button, resets the progress bar,
        and starts the worker thread for execution.
        """
        logging.debug("Starting diagnostics run.")
        self.run_button.setEnabled(False)
        self.progress_bar.setValue(0)

        self.run_worker = RunEvent(self)
        self.run_worker.start()
        self.run_worker.add_progress.connect(self.update_progress)
        self.run_worker.finished.connect(self.finish_run_event)

    def update_progress(self, value):
        """
        Update the progress bar based on worker progress.

        Args:
            value (int): The increment value to add to the progress bar.
        """
        self.progress_bar.setValue(self.progress_bar.value() + int(value))
        logging.debug(f"Progress updated by {value}%.")

    def finish_run_event(self):
        """
        Handle the completion of the diagnostics run.
        """
        self.run_button.setEnabled(True)
        self.progress_bar.setValue(100)
        QtWidgets.QMessageBox.information(self, "Info", "Task completed!!")
        logging.debug("Diagnostics run completed successfully.")

    def open_path(self, path: str):
        """
        Open a file or directory using the system's default handler.

        Args:
            path (str): File or directory path to open.
        """
        try:
            if path and os.path.exists(path):
                logging.info(f"Opening path: {path}")
                QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(path))
            else:
                logging.error(f"Invalid or non-existent path: {path}")
        except Exception as e:
            logging.exception(f"Failed to open path: {e}")
