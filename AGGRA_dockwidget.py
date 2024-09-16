# -*- coding: utf-8 -*-
"""
/***************************************************************************
 AGGRADockWidget
                                 A QGIS plugin
 An autonomous agent framework to select geospatial data and then fetch data by generating and executing programs with self-debugging.
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                             -------------------
        begin                : 2024-08-01
        git sha              : $Format:%H$
        copyright            : (C) 2024 by Geoinformation and Big Data Research Laboratory (GIBD)
        email                : tea5209@psu.edu
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
import base64
import configparser
import os

import requests
from qgis.PyQt import QtGui, QtWidgets, uic
from qgis.PyQt.QtCore import pyqtSignal




import os
import sys
from qgis.PyQt.QtCore import QSettings


from .install_packages.check_packages import check

API_EXIST = False
try:
    settings = QSettings()
    packages_installed = settings.value('AGGRA/PackagesInstalled', False, type=bool)

    if not packages_installed:


        check(['openai', 'langchain-openai', 'pyvis', 'nest-asyncio', 'rasterio', 'osmnx', 'geopandas', 'pyogrio',
               'fiona'])

    API_EXIST = True
finally:
    pass

#     import openai

    # API_EXIST = True

try:
    import threading
except:
    pass

import time
import traceback
from io import StringIO

from qgis.PyQt.QtCore import Qt, QCoreApplication
from qgis.PyQt import uic
from qgis.PyQt import QtWidgets
from qgis._core import QgsProject, QgsVectorLayer, QgsCoordinateReferenceSystem, \
    QgsCoordinateTransform, QgsFeature, Qgis
from qgis.utils import iface

QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)

from PyQt5.QtCore import QUrl, QThread, pyqtSignal, pyqtSlot, QSettings
from PyQt5.QtGui import QTextCursor

from PyQt5.QtWidgets import QGridLayout, QHBoxLayout, QWidget, QPushButton, QFileDialog, QMenu, QAction, QCompleter, \
    QVBoxLayout, QLineEdit, QTableWidgetItem, QDialog, QLabel, QMessageBox, QInputDialog
from qgis.gui import QgsPasswordLineEdit
from qgis.PyQt.QtWebKitWidgets import QWebView


FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'AGGRA_dockwidget_base.ui'))


class AGGRADockWidget(QtWidgets.QDockWidget, FORM_CLASS):

    closingPlugin = pyqtSignal()

    def __init__(self, parent=None):
        """Constructor."""
        super(AGGRADockWidget, self).__init__(parent)
        # Set default width
        # Set up the user interface from Designer.
        # After setupUI you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://doc.qt.io/qt-5/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect
        self.setupUi(self)
        # Set initial size of the plugin window
        self.set_initial_size(800, 600)  # Width: 800, Height: 600
        self.initUI()

        # Initialize conversation history
        self.conversation_history = []

        self.api_keys = {} # Dictionary to store API keys

        self.task_history = []
        self.saved_fname_history = []

        self.stopFlag = False
        # Initialize QCompleter for task_LineEdit
        self.task_completer = QCompleter(self.task_history, self)
        self.task_completer.setCaseSensitivity(Qt.CaseInsensitive)
        # self.task_LineEdit.setCompleter(self.task_completer)

        # Initialize QCompleter for data_pathLineEdit
        self.saved_fname_completer = QCompleter(self.saved_fname_history, self)
        self.saved_fname_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.saved_fnameLineEdit.setCompleter(self.saved_fname_completer)

        self.tabWidget = self.findChild(QtWidgets.QTabWidget, 'tabWidget')
        self.tab_3_index = self.tabWidget.indexOf(self.tab_3)

        # Set the initial tab to the first tab (change this to the desired tab)
        self.tabWidget.setCurrentIndex(0)


    def initUI(self):
        self.run_button = self.findChild(QPushButton, 'run_button')

        self.run_button.clicked.connect(self.run_script)

        self.run_button.clicked.connect(lambda: self.append_message(self.task_LineEdit.toPlainText()))

        self.interrupt_button.clicked.connect(self.interrupt)
        # self.chatgpt_ans.setReadOnly(True)  # Make the text edit read-only (if desired)
        self.chatgpt_ans.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)

        self.SelectDataPath_ToolBtn.clicked.connect(self.select_output_directory)

        self.clear_chatgpt_ansBtn.clicked.connect(self.clear_chatgpt_ans)

        self.interrupt_button.clicked.connect(self.stop_script)

        self.SelectDataPath_ToolBtn.clicked.connect(self.save_settings)

        self.task_LineEdit.textChanged.connect(self.save_settings)
        self.saved_fnameLineEdit.textChanged.connect(self.save_settings)
        # self.OpenAI_key_LineEdit.textChanged.connect(self.save_settings)
        self.modelNameComboBox.currentIndexChanged.connect(self.save_settings)
        self.SelectDataPath_ToolBtn.clicked.connect(self.save_settings)
        # Connect the button click to the method that adds a new row
        self.addkeyButton.clicked.connect(self.add_row)
        self.removekeyButton.clicked.connect(self.remove_row)

        # Initialize the row label counter
        self.row_label_counter = 0
        self.textBrowser.setOpenExternalLinks(True)

        # self.load_api_keys()
        self.setup_initial_rows()  # Set up initial rows in the table
        self.read_updated_config()

    def setup_initial_rows(self):
        initial_keys = ["OpenAI_key", "US_Census_key", "OpenWeather_key", "OpenTopography"]
        for key in initial_keys:
            self.add_row(key)
    def read_updated_config(self):
        current_script_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(current_script_dir, 'LLM_Find', 'config.ini')
        # config_path = os.path.join(os.path.dirname(self.script_path), 'config.ini')
        config = configparser.ConfigParser()
        config.read(config_path)
        if 'API_Key' in config:
            for row in range(self.tableWidget.rowCount()):
                key_name = self.tableWidget.cellWidget(row, 0).currentText()
                if key_name in config['API_Key']:
                    api_key = config['API_Key'][key_name]
                    self.tableWidget.cellWidget(row, 1).findChild(QgsPasswordLineEdit).setText(api_key)
    def add_row(self, key_name = None):
        # Get the current number of rows
        row_count = self.tableWidget.rowCount()
        # Insert a new row at the end
        self.tableWidget.insertRow(row_count)



        # Create a QWidget container for the QgsPasswordLineEdit
        container_widget = QtWidgets.QWidget()
        password_edit = QgsPasswordLineEdit(container_widget)


        # Set the layout for the container widget
        layout = QtWidgets.QHBoxLayout(container_widget)
        layout.addWidget(password_edit)
        layout.setContentsMargins(0, 0, 0, 0)  # Remove margins

        # Create a QComboBox for the first column
        combo_box = QtWidgets.QComboBox()
        names = ["OpenAI_key", "OpenWeather_key", "US_Census_key", "OpenTopography"]  # Replace with your list of names
        combo_box.addItems(names)

        if key_name:
            combo_box.setCurrentText(key_name)
        self.tableWidget.setCellWidget(row_count, 0, combo_box)


        # Set the API key if provided
        if key_name:
            settings = QSettings('YourOrganization', 'YourApplication')
            api_key = settings.value(f'API_Key/{key_name}', '')
            password_edit.setText(api_key)

        # Create a QLineEdit for the second column
        # password_edit = QgsPasswordLineEdit
        self.tableWidget.setCellWidget(row_count, 1, container_widget)
        self.tableWidget.setColumnWidth(1, 160)  # Adjust the width as needed

        # Increment the row label counter
        self.row_label_counter += 1
        # Adjust the table height
        self.adjust_table_height()

    def remove_row(self):
        # Get the selected row
        selected_row = self.tableWidget.currentRow()
        if selected_row >= 0:  # Ensure a row is selected
            self.tableWidget.removeRow(selected_row)
            # Adjust the table height
            self.adjust_table_height()



    def adjust_table_height(self):
        total_height = self.tableWidget.horizontalHeader().height()
        for row in range(self.tableWidget.rowCount()):
            total_height += self.tableWidget.rowHeight(row)
        self.tableWidget.setFixedHeight(total_height)

    def update_api_keys(self):
        self.api_keys = {}
        settings = QSettings('YourOrganization', 'YourApplication')
        for row in range(self.tableWidget.rowCount()):
            key_name = self.tableWidget.cellWidget(row, 0).currentText()
            api_key = self.tableWidget.cellWidget(row, 1).findChild(QgsPasswordLineEdit).text()
            self.api_keys[key_name] = api_key
            settings.setValue(f'API_Key/{key_name}', api_key)

    def load_api_keys(self):
        settings = QSettings('YourOrganization', 'YourApplication')
        for row in range(self.tableWidget.rowCount()):
            key_name = self.tableWidget.cellWidget(row, 0).currentText()
            api_key = settings.value(f'API_Key/{key_name}', '')
            self.tableWidget.cellWidget(row, 1).findChild(QgsPasswordLineEdit).setText(api_key)

    def set_initial_size(self, width, height):
        """Set the initial size of the plugin window."""
        self.resize(width, height)


    def closeEvent(self, event):
        self.closingPlugin.emit()
        event.accept()

    # def helpPage (self):
    #     """
    #             change the page of the manual according to the plot type selected and
    #             the language (looks for translations)
    #             """
    #
    #     # locale = QSettings().value('locale/userLocale', 'en_US')[0:2]
    #
    #     self.help_view.load(QUrl(''))
    #     self.layouth.addWidget(self.help_view)
    #     help_url = QUrl(
    #         'https://github.com/gladcolor/LLM-Find/blob/master/README.md')
    #     self.help_view.load(help_url)

    def save_settings(self):
        settings = QSettings('YourOrganization', 'YourApplication')

        settings.setValue('task', self.task_LineEdit.toPlainText())
        settings.setValue('saved_fname', self.saved_fnameLineEdit.text())
        # settings.setValue('OpenAI_key', self.OpenAI_key_LineEdit.text())
        settings.setValue('model_name', self.modelNameComboBox.currentText())

    def load_settings(self):
        settings = QSettings('YourOrganization', 'YourApplication')

        self.task_LineEdit.setPlainText(settings.value('task', ''))
        self.saved_fnameLineEdit.setText(settings.value('saved_fname', ''))
        # self.OpenAI_key_LineEdit.setText(settings.value('OpenAI_key', ''))
        self.modelNameComboBox.setCurrentText(settings.value('model_name', ''))

    def select_output_directory(self):
        file_dialog = QFileDialog(self, "Select Output Directory and Filename")
        file_dialog.setAcceptMode(QFileDialog.AcceptSave)
        file_dialog.setFileMode(QFileDialog.AnyFile)
        file_dialog.setDefaultSuffix("gpkg")
        file_dialog.setNameFilters([
            "GeoPackage (*.gpkg *.GPKG)",
            "Shapefile (*.shp)",
            "CSV files (*.csv)",
            "TIFF files (*.tif *.tiff *.TIF *.TIFF)",
            "PNG files (*.png *.PNG)",
            "All Files (*)"
        ])
        if file_dialog.exec_() == QFileDialog.Accepted:
            selected_file = file_dialog.selectedFiles()[0]
            self.saved_fnameLineEdit.setText(selected_file)
            self.saved_fname = selected_file

    def reproject_layer_to_wgs84(self, layer):
        wgs84_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        transform_context = QgsProject.instance().transformContext()
        transform = QgsCoordinateTransform(layer.crs(), wgs84_crs, transform_context)

        # Create a new layer with WGS84 CRS
        reprojected_layer = QgsVectorLayer(
            layer.dataProvider().dataSourceUri(),
            layer.name() + "_wgs84",
            "memory"
        )
        reprojected_layer.setCrs(wgs84_crs)
        reprojected_layer_data_provider = reprojected_layer.dataProvider()

        # Copy fields from the original layer
        reprojected_layer_data_provider.addAttributes(layer.fields())
        reprojected_layer.updateFields()

        # Reproject features and add to the new layer
        features = []
        for feature in layer.getFeatures():
            reprojected_feature = QgsFeature()
            reprojected_feature.setGeometry(feature.geometry().transform(transform))
            reprojected_feature.setAttributes(feature.attributes())
            features.append(reprojected_feature)

        reprojected_layer_data_provider.addFeatures(features)
        reprojected_layer.updateExtents()

        return reprojected_layer

    def openFileDialog(self):
        # Define the file filter
        file_filter = "Data files (*.csv *.shp *.geojson)"
        saved_fname, _ = QFileDialog.getOpenFileName(None, "Select Data Path", "", file_filter)
        if saved_fname:
            # Set the chosen path in the line edit widget
            self.saved_fnameLineEdit.setText(f"{saved_fname}")

    def run_script(self):
        self.update_api_keys()
        self.tabWidget.setCurrentIndex(self.tab_3_index)
        current_script_dir = os.path.dirname(os.path.abspath(__file__))
        script_path = os.path.join(current_script_dir, 'LLM_Find', 'LLM_FIND.py')
        # OpenAI_key = helper.load_OpenAI_key()
        # self.OpenAI_key = self.get_openai_key()  # Retrieve the API key from the line edit
        self.OpenAI_key = self.api_keys.get("OpenAI_key")
        self.model_name = self.modelNameComboBox.currentText()

        # self.task = self.task_LineEdit.text()
        self.task = self.task_LineEdit.toPlainText()
        self.saved_fname = self.saved_fnameLineEdit.text()
        filename_only = os.path.basename(self.saved_fname)  # .split('.')[0]

        # Add task to history and update completer
        if self.task not in self.task_history:
            self.task_history.append(self.task)
            self.task_completer.model().setStringList(self.task_history)

        # Add data path to history and update completer
        if self.saved_fname not in self.saved_fname_history:
            self.saved_fname_history.append(self.saved_fname)
            self.saved_fname_completer.model().setStringList(self.saved_fname_history)

        self.thread = ScriptThread(script_path, self.task, self.saved_fname, self.api_keys, self.model_name)

        # self.task = self.task_LineEdit.text()
        # self.saved_fname = self.saved_fnameLineEdit.text()
        # filename_only = os.path.basename(self.saved_fname)  # .split('.')[0]

        # Add task to history and update completer
        if self.task not in self.task_history:
            self.task_history.append(self.task)
            self.task_completer.model().setStringList(self.task_history)

        # Add data path to history and update completer
        if self.saved_fname not in self.saved_fname_history:
            self.saved_fname_history.append(self.saved_fname)
            self.saved_fname_completer.model().setStringList(self.saved_fname_history)

        self.thread.output_line.connect(self.update_output)
        # self.thread.graph_ready.connect(self.update_graph)
        # self.thread.graph_ready.connect(self.update_chatgpt_ans)
        # self.thread.GraphReady.connect(self.update_chatgpt_ans)
        self.thread.chatgpt_update.connect(self.update_chatgpt_ans)
        self.thread.finished.connect(self.thread_finished)
        self.thread.start()

    def stop_script(self):
        if self.thread:
            self.thread.terminate()
            self.update_chatgpt_ans(f"LLMQGIS: Script terminated")

            # print("Script terminated")

    def update_chatgpt_ans(self, message, is_user=False):
        # Append new message to conversation history
        self.conversation_history.append((message, is_user))
        self.chatgpt_ans.clear()
        for msg, user in self.conversation_history:
            self.append_text_with_format(msg, user)
            # self.chatgpt_ans.append(msg)
        self.chatgpt_ans.repaint()
        self.chatgpt_ans.verticalScrollBar().setValue(self.chatgpt_ans.verticalScrollBar().maximum())

    def append_text_with_format(self, text, is_user=True):
        cursor = self.chatgpt_ans.textCursor()
        cursor.movePosition(QTextCursor.End)

        if is_user:
            html = f'<div style="text-align: left; padding: 10px; margin: 5px; border: 2px solid blue; border-radius: 10px;">{text}</div>'
        else:
            html = f'<div style="text-align: right; padding: 10px; margin: 5px; border: 2px solid green; border-radius: 10px;">{text}</div>'

        cursor.insertHtml(html)
        cursor.insertHtml('<br>')  # Add a line break between messages
        # self.task_LineEdit.clear()

        self.chatgpt_ans.setTextCursor(cursor)

    @pyqtSlot(str)
    def append_message(self, message):
        message = self.task_LineEdit.toPlainText()
        if message.strip():  # Check if message is not empty
            # self.conversation_history.append(f"User: {message}")
            self.update_chatgpt_ans(f"User: {message}", is_user=True)
            self.update_chatgpt_ans(f"LLM-Find:Loading ...", is_user=False)
            # Clear the input field after sending the message
            # self.task_LineEdit.clear()

    def update_output(self, line):
        # self.output_text_edit.append(line)

        self.output_text_edit.insertPlainText(line)
        self.output_text_edit.insertPlainText('\n')  # Add a newline after each line
        self.output_text_edit.moveCursor(QTextCursor.End)  # Ensure cursor is at the end
        self.output_text_edit.repaint()

    def thread_finished(self, success):
        if success:
            # self.output_text_edit.append("The script ran successfully.")
            self.output_text_edit.insertPlainText("The script ran successfully.")
            self.update_chatgpt_ans(f"LLM-FIND: Done")
        else:
            # self.output_text_edit.append("The script finished with errors.")
            self.output_text_edit.insertPlainText("The script finished with errors.")
            self.update_chatgpt_ans(f"LLMFIND: The script finished with errors.")

    def clear_chatgpt_ans(self):
        self.output_text_edit.clear()

    def interrupt(self):
        if self.thread:
            self.thread.stop()  # Call the stop method to set the flag

    def get_api_key(self, key_name):
        return self.self.api_keys.get(key_name)

class ScriptThread(QThread):
    output_line = pyqtSignal(str)
    chatgpt_update = pyqtSignal(str)
    # graph_ready = pyqtSignal(str)
    # GraphReady = pyqtSignal(str)
    finished = pyqtSignal(bool)

    def __init__(self, script_path, task, saved_fname, api_keys, model_name):
        super().__init__()
        self.script_path = script_path
        self.task = task
        self.saved_fname = saved_fname
        self.api_keys = api_keys  # Store the api_keys dictionary
        self.model_name = model_name

    def run(self):


        try:
            # Update the config file with the API keys
            self.update_config_file()

            # #Re-read the config to ensure the keys are updated
            # self.read_updated_config()

            # Read the script content
            with open(self.script_path, "r") as script_file:
                script_content = script_file.read()

            # Ensure that the updated configuration is read by reloading the config
            config_path = os.path.join(os.path.dirname(self.script_path), 'LLM_Find', 'config.ini')
            config = configparser.ConfigParser()
            config.read(config_path)

            local_vars = {
                'task': self.task,
                'saved_fname': self.saved_fname,
                # 'OpenAI_key': self.OpenAI_key,  # Add OpenAI_key to local variables
                'model_name': self.model_name
            }
            # # Add each API key to local_vars
            # for key_name, api_key in self.api_keys.items():
            #     local_vars[key_name] = api_key

            # Redirect stdout and stderr to capture the output
            original_stdout = sys.stdout
            original_stderr = sys.stderr
            sys_stdout_capture = StringIO()
            sys_stderr_capture = StringIO()
            sys.stdout = sys_stdout_capture
            sys.stderr = sys_stderr_capture

            def emit_output():
                sys_stdout_capture.flush()
                sys_stderr_capture.flush()
                captured_stdout = sys_stdout_capture.getvalue()
                captured_stderr = sys_stderr_capture.getvalue()
                sys_stdout_capture.truncate(0)
                sys_stderr_capture.truncate(0)
                sys_stdout_capture.seek(0)
                sys_stderr_capture.seek(0)

                if captured_stdout:
                    for line in captured_stdout.splitlines(keepends=True):
                        if line.endswith('\n'):
                            self.output_line.emit(line.rstrip())
                        else:
                            # handle the case where the line doesn't end with a newline
                            self.output_line.emit(line)

                if captured_stderr:
                    for line in captured_stderr.splitlines(keepends=True):
                        if line.endswith('\n'):
                            self.output_line.emit(f"Error: {line.rstrip()}")
                        else:
                            # handle the case where the line doesn't end with a newline
                            self.output_line.emit(f"Error: {line}")

            # Execute the script using exec
            exec_globals = globals()
            exec_locals = local_vars

            # This will allow for real-time capturing and emitting of output
            import threading
            stop_thread = threading.Event()

            def monitor_output():
                while not stop_thread.is_set():
                    emit_output()
                    time.sleep(0.1)  # Adjust sleep time as needed

            monitor_thread = threading.Thread(target=monitor_output)
            monitor_thread.start()

            try:
                exec(script_content, exec_globals, exec_locals)
            finally:
                stop_thread.set()
                monitor_thread.join()

            # Emit any remaining output
            emit_output()

            # Restore original stdout and stderr
            sys.stdout = original_stdout
            sys.stderr = original_stderr

            # Emit success signal
            self.finished.emit(True)

        except Exception as e:
            # Print traceback error to the text_edit
            traceback_str = traceback.format_exc()
            self.output_line.emit(f"Error: {e}\n{traceback_str}")  # Emit any exceptions to the UI
            self.chatgpt_update.emit(f"Error: {e}\n{traceback_str}")  # Emit any exceptions)
            self.finished.emit(False)  # Signal failure

    def update_config_file(self):
        current_script_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(current_script_dir, 'LLM_Find', 'config.ini')
        # config_path = os.path.join(os.path.dirname(self.script_path), 'config.ini')
        config = configparser.ConfigParser()
        config.read(config_path)

        if 'API_Key' not in config:
            config['API_Key'] = {}

        for key_name, api_key in self.api_keys.items():
            config['API_Key'][key_name] = api_key

        with open(config_path, 'w') as configfile:
            config.write(configfile)

    # def read_updated_config(self):
    #     current_script_dir = os.path.dirname(os.path.abspath(__file__))
    #     config_path = os.path.join(current_script_dir, 'LLM_Find', 'config.ini')
    #     # config_path = os.path.join(os.path.dirname(self.script_path), 'config.ini')
    #     config = configparser.ConfigParser()
    #     config.read(config_path)
    #     if 'API_Key' in config:
    #         for row in range(self.tableWidget.rowCount()):
    #             key_name = self.tableWidget.cellWidget(row, 0).currentText()
    #             if key_name in config['API_Key']:
    #                 api_key = config['API_Key'][key_name]
    #                 self.tableWidget.cellWidget(row, 1).findChild(QgsPasswordLineEdit).setText(api_key)

    def stop(self):
        self._is_running = False

    def isRunning(self):
        return self._is_running


class ContributionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.plugin = parent  # Reference to the main plugin class

        self.setWindowTitle("Contribute to SpatialAnalysisAgent")
        self.setMinimumWidth(400)

        self.setWindowTitle("Contribute to Spatial Analysis Agent")
        layout = QVBoxLayout(self)

        # Add a label for instructions
        instructions = QLabel("Instructions for contribution:")
        layout.addWidget(instructions)

        # Instructional label
        instructions = QLabel("""
        <h3>How to Contribute</h3>
        <ol>
            <li><b>Fork this repository</b> on GitHub: <a href='https://github.com/Teakinboyewa/SpatialAnalysisAgent'>Click Here</a>.</li>
            <li><b>Clone your fork</b> to your local machine.</li>
            <li>Upload a TOML file using this dialog (it will go to your forked repository).</li>
            <li>After uploading, go to GitHub and <b>open a pull request</b> from your fork to the main repository.</li>
        </ol>
        """)
        instructions.setOpenExternalLinks(True)
        layout.addWidget(instructions)

        # File upload button
        self.upload_button = QPushButton("Upload TOML File to Fork")
        self.upload_button.clicked.connect(self.upload_toml_file)
        layout.addWidget(self.upload_button)

    def get_github_token(self):
        """Retrieve the GitHub token from the config file or prompt the user to enter one."""

        # Path to the configuration file
        current_script_dir = os.path.dirname(os.path.abspath(__file__))
        githubtokenConfig_path = os.path.join(current_script_dir, "config_files", "GitHubTokenConfig.ini")

        config = configparser.ConfigParser()

        try:
            # Check if the config file exists
            if os.path.exists(githubtokenConfig_path):
                # If the config file exists, read the token from it
                config.read(githubtokenConfig_path)
                token = config.get("GitHub", "token", fallback=None)

                # If no token found, prompt for token
                if not token:
                    token = self.prompt_for_token(githubtokenConfig_path)
                return token

            else:
                # If the config file doesn't exist, create it and prompt for token
                os.makedirs(os.path.dirname(githubtokenConfig_path), exist_ok=True)
                return self.prompt_for_token(githubtokenConfig_path)

        except (configparser.Error, IOError) as e:
            QMessageBox.warning(self, "Error", f"Failed to read or write the token configuration: {e}")
            return None

    def prompt_for_token(self, config_file_path):
        """Prompt the user for a GitHub token and store it in the config file."""
        token, ok = QInputDialog.getText(self, 'GitHub Token', 'Please enter your GitHub token:')
        if ok and token:
            self.save_github_token(config_file_path, token)
            return token
        else:
            return None

    def save_github_token(self, config_file_path, token):
        """Save the GitHub token to the configuration file."""
        config = configparser.ConfigParser()
        config.read(config_file_path)
        config["GitHub"] = {"token": token}

        with open(config_file_path, "w") as config_file:
            config.write(config_file)

    def check_if_fork_exists(self, token, username):
        repo = "Teakinboyewa/AutonomousGIS_GeodataRetrieverAgent"
        url = f"https://api.github.com/repos/{username}/AutonomousGIS_GeodataRetrieverAgent"

        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }

        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            return True  # The fork exists
        else:
            return False

    def upload_to_user_fork(self, token, file_path, username):
        repo = f"{username}/AutonomousGIS_GeodataRetrieverAgent"  # Target the user's fork
        FOLDER_IN_REPO = "LLM_Find/Handbooks"  # Folder inside the repo
        file_name =os.path.basename(file_path)
        path_in_repo = f"{FOLDER_IN_REPO}/{file_name}"
        url = f"https://api.github.com/repos/{repo}/contents/{path_in_repo}"



        headers = {
            "Authorization": f"token {token}",

            "Accept": "application/vnd.github.v3+json"
        }

        # Check if the file already exists to get its S
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            file_data = response.json()
            sha = file_data["sha"]  # Get the SHA of the existing file
            file_exists = True
        elif response.status_code == 404:
            file_exists = False
            sha = None  # File doesn't exist, no SHA needed
        else:
            print(f"Error checking file existence: {response.json()}")
            raise Exception(f"Error checking file existence: {response.json()}")

        # Read the file content to upload
        with open(file_path, 'rb') as file:
            content = file.read()

        encoded_content = base64.b64encode(content).decode("utf-8")

        data = {
            "message": "Adding a new TOML file via QGIS plugin",
            "content": encoded_content
        }

        # If the file exists, include the SHA to update it
        if file_exists:
            data["sha"] = sha

        response = requests.put(url, json=data, headers=headers)

        if response.status_code in[200,201]:
            print("File successfully uploaded/updated in the forked GitHub repository.")
        else:
            print(f"Failed to upload/update file: {response.json()}")
            raise Exception(f"GitHub upload/update failed: {response.json()}")

        # if response.status_code == 201:
        #     print("File successfully uploaded to the forked GitHub repository.")
        # else:
        #     print(f"Failed to upload file: {response.json()}")
        #     raise Exception(f"GitHub upload failed: {response.json()}")

    def prompt_pull_request(self, username):
        pr_url = f"https://github.com/{username}/SpatialAnalysisAgent/compare"
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Information)
        msg.setText(
            f"File uploaded successfully to your fork.\nPlease open a pull request to merge it into the main repository.")
        msg.setInformativeText(f"<a href='{pr_url}'>Click here to open a pull request</a>")
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec_()

    def upload_toml_file(self):
        """Handle the file upload to the user's fork."""
        token = self.get_github_token()  # Get GitHub token from main plugin

        if not token:
            QMessageBox.warning(self, "Error", "GitHub token is required.")
            return

        # Prompt user to select a file
        file_dialog = QFileDialog(self)
        toml_files, _ = file_dialog.getOpenFileNames(self, "Select a TOML file", "", "TOML Files (*.toml)")

        if toml_files:
            # Ask for GitHub username (you can automate this with the token if preferred)
            username, ok = QInputDialog.getText(self, 'GitHub Username', 'Enter your GitHub username:')

            if ok and username:
                for toml_file in toml_files:
                    # Upload the file to the user's fork
                    self.upload_to_user_fork(token, toml_file, username)

                # Prompt the user to open a pull request
                self.prompt_pull_request(username)
            else:
                QMessageBox.warning(self, "Error", "GitHub username is required.")