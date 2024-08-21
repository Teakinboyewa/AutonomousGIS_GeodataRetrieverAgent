# Autonomous GIS - GeoData Retrieve Agent
The GeoData Retriever Agent is a plugin integration of an autonomous GIS agent for geospatial data retrieval and QGIS. This plugin simplifies the process of retrieving and loading geospatial data into the QGIS environment through natural language commands. It leverages [LLM-Find](https://github.com/gladcolor/LLM-Find), an autonomous framework designed to select and fetch geospatial data by generating and executing programs with self-debugging capabilities. For more details on the frame work, please refer to the [LLM-Find](https://github.com/gladcolor/LLM-Find) and our manuscript: Huan Ning, Zhenlong Li, Temitope Akinboyewa, and M. Naser Lessani. 2024. “An Autonomous GIS Agent Framework for Geospatial Data Retrieval.” arXiv. [https://doi.org/10.48550/arXiv.2407.21024](https://doi.org/10.48550/arXiv.2407.21024). 

# User Manual
The User Manual is available [here](https://github.com/Teakinboyewa/AutonomousGIS_GeodataRetrieverAgent/blob/master/User_manual.md)

# Plugin Interface

![Plugin Interface.png](Docs%2FPluginGUI.png)

![Settings.png](Docs%2FPluginSetting.png)

Note: API keys input here will only be stored locally on the user's computer ('plugin_dir/LLM-Find/config.ini').  

# Usage
Find some usage example on the Data Request [Examples](https://github.com/Teakinboyewa/AutonomousGIS_GeodataRetrieverAgent/blob/master/Data%20request%20examples.md) page

# MacOS users
## After the installation of the plugin, you need to install the "nest_asyncio" manually. Follow the steps below:
- Open the QGIS Python Console by navigating to ```Plugins``` > ```Python Console``` or press ```Ctrl+Alt+P```
- In the console, run these two lines of code:
  ```python
  import pip
  pip.main(['install', 'nest-asyncio'])
- If you encounter any issue you can also try installing "nest_asyncio" via the terminal by pointing to QGIsS python interpreter:
  
  ```python
  /Applications/QGIS3.38.1.app/Contents/MacOS/bin/python3 -m pip install nest_asyncio


# YouTube Channel
Some video demonstrations have been created on our [YouTubeChannel](https://youtube.com/@gibd_lab). Feel free to subscribe to the our YouTube channel dor regular updates.
