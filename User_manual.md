#  Autonomous GIS - Geodata Retrieve Agent User Manual
# Installation Guide

# Installation
- In QGIS, ```select Plugins``` > ```Manage and Install Plugins...```
- Find ```AutonomousGIS_GeoDataRetrieverAgent``` and click ```Install Plugin```

Alternatively,

- [Download](https://github.com/Teakinboyewa/AutonomousGIS_GeodataRetrieverAgent/archive/refs/heads/master.zip) the master repository of the plugin from github
- Launch QGIS software and navigate to ```Plugin >  Manage and install Plugins.. > Install from ZIP```
- Click on ```...``` to select the directory of the downloaded zip file and ```Install plugin```

![Install_Plugin1.png](Docs%2FInstall_Plugin1.png) 

- Click ```Yes``` to install all missing dependencies.
  
![Install dependencies.png](Docs%2FInstall%20dependencies.png)

- If successful, a success message will be displayed, then you can close the ```Plugins``` dialog. If you face any difficulty in installing any dependencies click here ([learn more about installing dependencies]())

![Plugin installation success.png](Docs%2FPlugin%20installation%20success.png)

# MacOS users
## After the installation of the plugin, you need to install the "nest_asyncio" manually. Follow the steps below:
- Open the QGIS Python Console by navigating to ```Plugins``` > ```Python Console``` or press ```Ctrl+Alt+P```
- In the console, run these two lines of code:
  ```python
  import pip
  pip.main(['install', 'nest-asyncio'])
- If you encounter any issue you can also try installing "nest_asyncio" via the terminal by pointing to QGIS python interpreter:
  
  ```python
  /Applications/QGIS3.38.1.app/Contents/MacOS/bin/python3 -m pip install nest_asyncio

- Restart the QGIS Software.
- Navigate to ```Plugins > Manage and install plugins```.  Ensure the plugin is checked.

![CheckBox.png](Docs%2FCheckBox.png)

# Opening the Plugin

- Load the ```Autonomous GIS - GeoData Retrieve Agent``` on ```Plugins```on menubar, or via its icon on the plugins toolbar.

![Plugin icon on toolbar.png](Docs%2FPlugin%20icon%20on%20toolbar.png)

# How to Use the Plugin
- The plugin interface consists of three tabs - ```Data Request Page```, ```Settings```, and ```Help```
- Data requests are made in the ```Data Request Page```. This consists of the ```Code pad``` which displays the AI-generated codes, ```Information Panel``` which displays the agent running information, ```Data request message panel``` which enables the user to enter the resuest message in natural language command, and the ```Output dirctory``` which enables user to set the desired path to save the downloaded data.

![Plugin Interface.png](Docs%2FPlugin%20Interface.png)

- The ```Settings``` tab, enable the user to select models and to set the Openai API keys and other data sources API keys. Find more details about [OpenAI API key](https://platform.openai.com/account/api-keys) and [data sources](https://github.com/Teakinboyewa/AutonomousGIS_GeodataRetrieverAgent/blob/master/User_manual.md#data-sources)

![PluginSetting.png](Docs%2FPluginSetting.png)

Note: API keys input here will only be stored locally on the user's computer ('plugin_dir/LLM-Find/config.ini').  

# Data Request Instructions

To make a data request, follow these steps:
- In the ```Data Request Message Panel```, type your data request using natural language.
- Specify the directory where you want the downloaded data to be saved.
- Enter your OpenAI API key and any other data source keys if required. Note: These API keys will be saved automatically in the ```config.ini``` file and will be used for any future data requests after this initial input.
- On the ```Data Request Page```, click the Send button to submit your request. Note: For the first request, it may take a minute to establish a connection to the OpenAI server.
- To stop a request, use the ```Interrupt``` button. This button is especially useful if you need to terminate a request. Additionally, the ```Clear``` button can be used to clear the code pad panel if needed.

## Data Sources
- [Openstreetmap:](https://www.openstreetmap.org/) administrative boundaries, street networks, points of interests (POIs) can be downloaded from this source.
- [US Census Bureau boundary:]() provides the US administrative boundaries (nation, state, county, tract, and block group level, as well as metropolitan statistic areas. API key is required. You can get an API key [here.]()
- [US Census Bureau demography:]() provides the demographic and socio-economic data, such as population, gender, income, education, and race.
- [US COVID-19 data by New York Times:]() provides the cumulative counts of COVID-19 cases and deaths in the United States, at the state and county level, over time from 2020-01-21 to 2023-03-23.
- [OpenWeather data:]() provides historical, current, and forecast weather data. The historical data can be back to 2023-08. [API]() limited: ```[Hourly forecast: 4 days, Daily forecast: 16 days, 3 hour forecast: 5 days]``` 
- [ESRI World Imagery (for export):]() It is a web map service, providing satellite image tiles. You can download tiles and mosaic them into a large image.
- [OpenTopography](https://opentopography.org/). You can download global digital elevation model (DEM) data using API (get one [here](https://opentopography.org/blog/introducing-api-keys-access-opentopography-global-datasets)); the resolution ranges from 15m to 1000m, such as SRTM GL3 (global 90m), and GL1 (global 30m). The DEM source list from this API contains: SRTMGL3, SRTMGL1, SRTMGL1_E, AW3D30, AW3D30, SRTM15Plus, NASADEM, COP30, COP30, EU_DTM, GEDI_L3, GEBCOIceTopo, GEBCOSubIceTopo.

## Data Request Examples
- Data request examples and video demonstrations for each data sources are available [here](https://github.com/Teakinboyewa/AutonomousGIS_GeodataRetrieverAgent/blob/master/Data%20request%20examples.md).
