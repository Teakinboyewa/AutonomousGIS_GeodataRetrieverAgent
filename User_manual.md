#  AutonomousGIS_GeodataRetrieverAgent USER MANUAL
# Installation Guide
- [Download](https://github.com/Teakinboyewa/AutonomousGIS_GeodataRetrieverAgent/archive/refs/heads/master.zip) the master repository of the plugin from github
- Launch QGIS software and navigate to ```Plugin >  Manage and install Plugins.. > Install from ZIP```
- Click on ```...``` to select the directory of the downloaded zip file and ```Install plugin```

![Install_Plugin1.png](Docs%2FInstall_Plugin1.png) 

- Click ```Yes``` to install all missing dependencies.

![Install dependencies.png](Docs%2FInstall%20dependencies.png)

- If successful, a success message will be displayed, then you can close the ```Plugins``` dialog. If you have any challenge in installing any dependencies click here ([learn more about installing dependencies]())

![Plugin installation success.png](Docs%2FPlugin%20installation%20success.png)

- Restart the QGIS Software.
- Navigate to ```Plugins > Manage and install plugins```.  Ensure the plugin is checked.

![CheckBox.png](Docs%2FCheckBox.png)

- Load the AutonomousGis_GeodataRetrieverAgent on ```Plugins```on menubar, or via its icon on the plugins toolbar.

![Plugin icon on toolbar.png](Docs%2FPlugin%20icon%20on%20toolbar.png)

# How to use the Plugin
- The plugin interface consists of three tabs - ```Data Request Page```, ```Settings```, and ```Help```
- Data requests are made in the ```Data Request Page```. This consists of the ```Code pad``` which displays the AI-generated codes, ```Information Panel``` which displays the agent running information, ```Data request message panel``` which enables the user to enter the resuest message in natural language command, and the ```Output dirctory``` which enables user to set the desired path to save the downloaded data.

![Plugin Interface.png](Docs%2FPlugin%20Interface.png)

- The ```Settings``` tab, enable the user to select models and to set the Openai API keys and other data sources API keys. Find more details about [OpenAI API key](https://platform.openai.com/account/api-keys) and [data sources](https://github.com/Teakinboyewa/AutonomousGIS_GeodataRetrieverAgent/blob/master/User_manual.md#data-sources)
![Settings.png](Docs%2FSettings.png)

# Data request Instructions

To make a data request, follow these steps:
- In the ```Data Request Message Panel```, type your data request using natural language.
- Specify the directory where you want the downloaded data to be saved.
- Enter your OpenAI API key and any other data source keys if required. Note: These API keys will be saved automatically in the ```config.ini``` file and will be used for any future data requests after this initial input.
- On the ```Data Request Page```, click the Send button to submit your request. Note: On every first request, it may take some few minutes to get the OpenAI response.
- To stop a request, use the ```Interrupt``` button. This button is especially useful if you need to terminate a request. Additionally, the ```Clear``` button can be used to clear the code pad panel if needed.
- Data request examples and video demonstrations are available [here](https://github.com/Teakinboyewa/AutonomousGIS_GeodataRetrieverAgent/blob/master/User_manual.md#data-request-examples).
## Data sources

## Data request Examples
