import os
import sys
import asyncio
import nest_asyncio
from qgis._core import QgsRasterLayer
from qgis.core import QgsVectorLayer, QgsProject
from IPython import get_ipython
import rasterio
from PIL import Image
import requests
import networkx as nx
import pandas as pd
import geopandas as gpd
# from pyvis.network import Network
from openai import OpenAI
from IPython.display import display, HTML, Code
from IPython.display import clear_output
import matplotlib.pyplot as plt
import base64
import pickle
import osmnx as ox

# Enable autoreload
ipython = get_ipython()
if ipython:
    ipython.run_line_magic('load_ext', 'autoreload')
    ipython.run_line_magic('autoreload', '2')


# Get the directory of the current script
current_script_dir = os.path.dirname(os.path.abspath(__file__))
llm_find_dir = os.path.join(current_script_dir, 'LLM_Find')

# Add the directory to sys.path
if current_script_dir not in sys.path:
    sys.path.append(llm_find_dir)

# Now you can import the module
import LLM_Find_Constants as constants
import LLM_Find_helper as helper


import numpy as np
# from LLM_Find_kernel import Solution

from langchain_openai import ChatOpenAI

# from langchain_core.prompts import ChatPromptTemplate

# OpenAI_key = helper.load_OpenAI_key()

# ---- Data source 1:  OpenStreetMap  -----------------

## task_name ='Nigeria_cities'
# downloaded_file_name = r'Nigeria_cities.gpkg'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download the city locations of Nigeria; do not download towns.
# 2. Save the downloaded data as points, save it at: {saved_fname}
# '''

# task_name ='Nigeria_rivers'
# downloaded_file_name = r'Nigeria_rivers.gpkg'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download the rivers of Nigeria.
# 2. Save the downloaded data as polylines, save it at: {saved_fname}
# '''

# task_name ='Nigeria_state_boundary'  # most test failed!!!!! Soloved.
# downloaded_file_name = r'Nigeria_states_boundary.gpkg'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download all state boundaries of Nigeria.
# # 2. Save the downloaded data as polygons, save it at: {saved_fname}
# # '''

# task_name ='World_country_boundary'  # most test failed!!!!! Soloved.
# downloaded_file_name = r'World_country_boundary.gpkg'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download all country boundaries of the world.
# # 2. Save the downloaded data as polygons, save it at: {saved_fname}
# # '''


## task_name ='China_mainland_province_boundary'  # most test failed! solved.
# downloaded_file_name = r'China_mainland_Province_boundary.gpkg'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download all province boundaries of China mainland.
# 2. Save the downloaded data as polygons in GeoPackage format at: {saved_fname}
# '''

## task_name ='OSM_PA_boundary'
# downloaded_file_name = r'PA_boundary.gpkg'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download the administrative boundary of Pennsylvania State, USA.
# 2. Save the downloaded data in GeoPackage format, save it at: {saved_fname}
# '''

## task_name ='OSM_SC_boundary'
# downloaded_file_name = r'SC_boundary.gpkg'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download the administrative boundary of South Carolina State, USA.
# 2. Save the downloaded data in GeoPackage format at: {saved_fname}
# '''

# task_name ='OSM_PA_hospital'
# downloaded_file_name = r'PA_hospital.gpkg'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download all hospitals in Pennsylvania, USA.
# 2. Save the downloaded data as points in GeoPackage format at: {saved_fname}
# '''

## task_name ='SC_hospital'
# downloaded_file_name = r'SC_hospital.gpkg'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download all hospitals in South Carolina, USA.
# 2. Save the downloaded data as points in GeoPackage at: {saved_fname}
# '''

## task_name ='OSM_SC_school'
# downloaded_file_name = r'SC_school.gpkg'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download all schools in South Carolina State, USA.
# 2. Save the downloaded data as points in GeoPackage format at: {saved_fname}
# '''

# task_name ='OSM_Yulin_River'
# downloaded_file_name = r'Yulin_river.gpkg'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download all rivers in Yulin, Guangxi, China.
# 2. Save the downloaded data as polylines in GeoPackage format at: {saved_fname}
# '''

## task_name ='OSM_CA_park'
# downloaded_file_name = r'CA_parks.gpkg'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download all parks in California, USA, including urban public, recreation, state, and national parks.
# 2. Save the downloaded data as points in GeoPackage format at: {saved_fname}
# # '''

## task_name ='OSM_USA_university'
# downloaded_file_name = r'USA_universities.gpkg'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download the POIs of all universities, colleges, and other higher education institutions in the USA.
# 2. Save the downloaded data as points in GeoPackage format at: {saved_fname}
# '''

## task_name ='OSM_State_College_street'
# downloaded_file_name = r'State_College_street.gpkg'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download all streets of State College, Pennsylvania, USA.
# 2. Save the downloaded data as polylines in GeoPackage format at: {saved_fname}
# '''

# ## task_name ='OSM_Nigeria_boundary'
# downloaded_file_name = r'Nigeria_boundary.gpkg'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download the administrative boundary of Nigeria.
# 2. Save the downloaded data in GeoPackage format at: {saved_fname}
# '''

# ## task_name ='OSM_Afghanistan_boundary'
# downloaded_file_name = r'Afghanistan_boundary.gpkg'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download the administrative boundary of Afghanistan.
# 2. Save the downloaded data in GeoPackage format at: {saved_fname}
# '''


# task_name ='OSM_Nigeria_railway'
# downloaded_file_name = r'Nigeria_railway.gpkg'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download the railway network of Nigeria.
# 2. Save the downloaded data in GeoPackage format, save it at: {saved_fname}
# '''

## task_name ='Wuhan_railway_network'
# downloaded_file_name = r'Wuhan_Railway_network.gpkg'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download the railway network in Wuhan, Hubei, China.
# 2. Save the downloaded data as polylines in GeoPackage format at: {saved_fname}
# '''
# # Wuhan_railway_network is a difficult case! It succeeded at the beginning, but failed all the time later.
# # The query: area["name"="Wuhan"]["boundary"="administrative"]->.searchArea; is not correct. Need to use "name:en".
# # Using "Hubei Province" may not return polygons

## task_name ='Qingdao_boundary'
# downloaded_file_name = r'Qingdao_boundary.gpkg'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download the administrative of Qingdao, Shandong, China.
# 2. Save the downloaded data as polygons, save it at: {saved_fname}
# '''

# task_name ='China_Guangdong_province_boundary'
# downloaded_file_name = r'China_Guangdong_province_boundary.gpkg'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download the Guangdong province boundaries of China.
# 2. Save the downloaded data as polygons, save it at: {saved_fname}
# '''

## task_name ='OSM_coffee_shop_Vietnam'
# downloaded_file_name = r'coffee_shop_Vietnam.gpkg'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download all the coffee shops in Vietnam.
# 2. Save the downloaded data in GeoPackage format, save it at: {saved_fname}
# '''


#------------------------------## Data source 2:  US Census Bureau administrative boundary

## task_name ='Census_SC_tract'
# downloaded_file_name = r'Census_SC_tract.gpkg'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download all census tract boundaries in South Carolina, USA.
# 2. Save the downloaded data as polygons in GeoPackage format, save it at: {saved_fname}
# '''

# task_name ='Census_SC_blockgroups'
# saved_fname = r'E:\OneDrive_PSU\OneDrive - The Pennsylvania State University\Research_doc\LLM-Find\Downloaded_Data\Census_SC_blockgroups.gpkg'
# if os.path.exists(saved_fname):
#     os.remove(saved_fname)
# task = rf'''1. Download all Census block group boundaries in South Carolina, USA.
# 2. Save the downloaded data as polygons in GeoPackage format, save it at: {saved_fname}
# '''

# task_name ='Census_Centre_boundary'
# saved_fname = r'E:\OneDrive_PSU\OneDrive - The Pennsylvania State University\Research_doc\LLM-Find\Downloaded_Data\Census_Centre_boundary.gpkg'
# task = rf'''1. Download the administrative boundary of Centre County of Pennsylvania State, USA from Census Bureau.
# 2. Save the downloaded data in GeoPackage format, save it at: {saved_fname}
# '''

# task_name ='Census_SC_countries_boundary'
# saved_fname = r'E:\OneDrive_PSU\OneDrive - The Pennsylvania State University\Research_doc\LLM-Find\Downloaded_Data\Census_SC_counties_boundary.gpkg'
# task = rf'''1. Download the administrative boundary of all Counties of South Carolina from Census Bureau.
# 2. Save the downloaded data in GeoPackage format, save it at: {saved_fname}
# '''

# # task_name ='US_Carolinas_tract"
# downloaded_file_name = r'US_Carolinas_tract.gpkg'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download all the Census tract boundaries of North Carolina and South Carolina in the USA.
# 2. Save the downloaded data in GeoPackage format at: {saved_fname}
# '''

# # task_name ='US_county_boundary"
# downloaded_file_name = r'US_county_boundary.gpkg'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download all the county boundaries in the USA.
# 2. Save the downloaded data in GeoPackage format at: {saved_fname}
# '''



#__________________________________Data source 3:  US Census Bureau demographic variables____#API KEY NEEDED_____________________________________________________
# task_name ='Census_SC_counties_population'
# saved_fname = r'E:\OneDrive_PSU\OneDrive - The Pennsylvania State University\Research_doc\LLM-Find\Downloaded_Data\Census_SC_counties_population.csv'
# task = rf'''1. Download latest population for each county in South Carolina.
# 2. Save the downloaded data as CSV files, save it at: {saved_fname}
# '''

# task_name ='Census_SC_Richland_race_population'
# saved_fname = r'E:\OneDrive_PSU\OneDrive - The Pennsylvania State University\Research_doc\LLM-Find\Downloaded_Data\Census_SC_Richland_race_population.csv'
# task = rf'''1. Download latest population of each race for Richland county in South Carolina, at Census block group level.
# 2. Save the downloaded data as CSV files, save it at: {saved_fname}
# '''

# task_name ='Census_PA_counties_race_population'
# saved_fname = r'E:\OneDrive_PSU\OneDrive - The Pennsylvania State University\Research_doc\LLM-Find\Downloaded_Data\Census_PA_counties_race_population.csv'
# task = rf'''1. Download latest population by race for all counties in Pennsylvania.
# 2. Save the downloaded data as CSV files, save it at: {saved_fname}
# '''

# task_name ='Census_US_states_population'
# saved_fname = r'E:\OneDrive_PSU\OneDrive - The Pennsylvania State University\Research_doc\LLM-Find\Downloaded_Data\Census_US_states_population.csv'
# task = rf'''1. Download latest population for all states in USA.
# 2. Save the downloaded data as CSV files, save it at: {saved_fname}
# '''

# task_name ='Census_US_states_education_population'
# saved_fname = r'E:\OneDrive_PSU\OneDrive - The Pennsylvania State University\Research_doc\LLM-Find\Downloaded_Data\Census_US_states_education_population.csv'
# task = rf'''1. Download latest population by higher education attainment over 25 for all states in USA, together with the entire population of each state.
# 2. Save the downloaded data as CSV files, save it at: {saved_fname}
# '''

# task_name ='Census_US_county_household_income'
# saved_fname = r'E:\OneDrive_PSU\OneDrive - The Pennsylvania State University\Research_doc\LLM-Find\Downloaded_Data\Census_US_county_household_income.csv'
# task = rf'''1. Download the latest median household income data for each county in the USA.
# 2. Save the downloaded data as CSV files, save it at: {saved_fname}
# '''

# task_name ='Census_US_county_population_by_race'
# saved_fname = r'E:\OneDrive_PSU\OneDrive - The Pennsylvania State University\Research_doc\LLM-Find\Downloaded_Data\Census_US_county_population_by_race.csv'
# task = rf'''1. Download the latest population by race data for each county in the USA.
# 2. Save the downloaded data as CSV files, save it at: {saved_fname}
# '''

# # task_name ='States_colledge_popultion'   # difficult to get the correct variable combination.
# downloaded_file_name = r'States_colledge_popultion.csv'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download the population over 25 years old and the population with a college degree or higher at the state level of USA for 2012 and 2022.
# 2. Save the downloaded data in CSV format, save it at: {saved_fname}
# '''

## task_name ='US_SDOH'   # difficult to get the correct variable combination
# downloaded_file_name = r'US_SDOH.csv'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download the social determinators of health, including: 1) population of each race; 2) Median household income; 3) health insurance coverage; 4) Population of speaking only English at home for the population 5 years and over.
# 2. The data should be at the county level in the USA. Year: 2022.
# 3. Save the downloaded data in a CSV file, save it at: {saved_fname}
# '''

# task_name ='US_County_poverty'
# saved_fname = r'E:\OneDrive_PSU\OneDrive - The Pennsylvania State University\Research_doc\LLM-Find\Downloaded_Data\US_County_poverty.csv'
# task = rf'''1. Download the ratios of income to all poverty level at the county level in the USA. Year: 2022.
# 3. Save the downloaded data in a CSV file, save it at: {saved_fname}
# '''

## task_name ='Washington_DC_blockgroup_senior_population'
# downloaded_file_name = r'Washington_DC_blockgroup_senior_population.csv'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task_name ='Washington_DC_blockgroup_senior_population'
# task = rf'''1. Download the senior (older than  65) population groups senior  for all Census blockgroups in Washington D.C., USA.
# 2. Save the downloaded data as CSV files, save it at: {saved_fname}
# '''

# task_name ='School_enrollment'
# saved_fname = r'E:\OneDrive_PSU\OneDrive - The Pennsylvania State University\Research_doc\LLM-Find\Downloaded_Data\School_enrollment_population.csv'
# task = rf'''1. From Census 2020 data, download the school enrollment by level of school for the population 3 years and over of all Census block groups in San Francisco County, California, USA.
# 2. Save the downloaded data as CSV files, save it at: {saved_fname}
# '''




#_______________________________________Data source 4:  COVID-19 accumulative cases by New York Times____________________________________________________
## task_name ='COVID_Richland_SC'
# downloaded_file_name = r'COVID_Richland_SC.csv'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download the COVID-19 case data of Richland County in South Carolina, USA. The time is from 2021-01 to 2021-09.
# 2. Save the downloaded data as a CSV file at: {saved_fname}
# '''

# task_name ='COVID_PA'
# downloaded_file_name = r'COVID_PA.csv'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download the COVID-19 case data of all counties in Pennsylvania, USA. The time is from 2021-10 to 2022-02.
# 2. Save the downloaded data as a CSV file at: {saved_fname}
# '''

# task_name ='COVID_PA'
# downloaded_file_name = r'COVID_NJ_NY.csv'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download the COVID-19 case data of all counties in Pennsylvania State and New York State, USA. The period is entire 2021.
# 2. Save the downloaded data as a CSV file at: {saved_fname}
# '''




#______________________________________Data source 5: Weather data ________#API Key needed____________________________________________
## task_name ='OpenWeather_Columbia'
# downloaded_file_name = r'OpenWeather_Columbia.csv'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download the historical weather data of Columbia, South Carolina in May 2024.
# 2. Save the downloaded data in CSV format, save it at: {saved_fname}
# '''

# # task_name ='OpenWeather_Yulin_Guangxi'
# downloaded_file_name = r'OpenWeather_Yulin_Guangxi.csv'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download the historical weather data of Yulin, Guangxi, China, in May 2024.
# 2. Save the downloaded data in CSV format, save it at: {saved_fname}
# '''

## task_name ='OpenWeather_Cairo'
# downloaded_file_name = r'OpenWeather_Cairo.csv'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download the current weather data of Cairo, Egypt.
# 2. Save the downloaded data in CSV format, save it at: {saved_fname}
# '''

## task_name ='OpenWeather_Kabul'
# downloaded_file_name = r'OpenWeather_Kabul.csv'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download the 16-day daily forecast weather data of Kabul, Afghanistan.
# 2. Save the downloaded data in CSV format, save it at: {saved_fname}
# '''




#________________________________Data source 6:  Satellite image (ESRI World Imagery (for export))_____________________________

# task_name ='FAST_Telescope'
# downloaded_file_name = r'FAST_Telescope_image.tif'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download the FAST Telescope (Guizhou, China) satellite image at level 18.
# 2. Save the downloaded data in tiff format, save it at: {saved_fname}
# '''

# # task_name ='Nigeria_image'
# downloaded_file_name = r'Nigeria_image.tif'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download the Nigeria satellite image at level 7.
# 2. Save the downloaded data in tiff format, save it at: {saved_fname}
# '''

# # task_name ='Qingdao_image'
# downloaded_file_name = r'Qingdao_image.tif'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download the Qingdao, Shandong, China satellite image at level 10.
# 2. Save the downloaded data in tiff format, save it at: {saved_fname}
# '''

# ## task_name ='Crescent_Moon_Spring'
# downloaded_file_name = r'Crescent_Moon_Spring_image.tif'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download the Singing-Sand Mountain and Crescent Moon Spring satellite image at level 16.
# 2. Save the downloaded data in tiff format, save it at: {saved_fname}
# '''

## task_name ='Christ the Redeemer'  # this is a point: a difficult case
# downloaded_file_name = r'Christ_the_Redeemer.tif'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download the Christ the Redeemer satellite image at level 18.
# 2. Save the downloaded data in tiff format, save it at: {saved_fname}
# '''

# #task_name ='Brasília_image'   # not ready yet
# saved_fname = r'E:\OneDrive_PSU\OneDrive - The Pennsylvania State University\Research_doc\LLM-Find\Downloaded_Data\Brasília_image.tif'
# task = rf'''1. Download the Brasília satellite image at level 6.
# 2. Save the downloaded data in tiff format, save it at: {saved_fname}
# '''

## task_name ='Japan_image'
# saved_fname = r'E:\OneDrive_PSU\OneDrive - The Pennsylvania State University\Research_doc\LLM-Find\Downloaded_Data\Japan_image.tif'
# task = rf'''1. Download the Japan satellite image at level 6.
# 2. Save the downloaded data in tiff format, save it at: {saved_fname}
# '''

## task_name ='China'
# saved_fname = r'E:\OneDrive_PSU\OneDrive - The Pennsylvania State University\Research_doc\LLM-Find\Downloaded_Data\China_image.tif'
# task = rf'''1. Download the China satellite image at level 6.
# 2. Save the downloaded data in tiff format, save it at: {saved_fname}
# '''

# task_name ='YellowStone_National_Park'
# saved_fname = r'E:\OneDrive_PSU\OneDrive - The Pennsylvania State University\Research_doc\LLM-Find\Downloaded_Data\Yellow_Stone_National_Park_image.tif'
# task = rf'''1. Download the YellowStone National Park satellite image at level 10.
# 2. Save the downloaded data in tiff format, save it at: {saved_fname}
# '''

## task_name ='Hawaii'
# saved_fname = r'E:\OneDrive_PSU\OneDrive - The Pennsylvania State University\Research_doc\LLM-Find\Downloaded_Data\Hawaii_image.tif'
# task = rf'''1. Download the Hawaii State satellite image at level 7.
# 2. Save the downloaded data in tiff format, save it at: {saved_fname}
# '''

## task_name ='Honolulu'
# saved_fname = r'E:\OneDrive_PSU\OneDrive - The Pennsylvania State University\Research_doc\LLM-Find\Downloaded_Data\Honolulu_image.tif'
# task = rf'''1. Download the Honolulu satellite image at level 12.
# 2. Save the downloaded data in tiff format, save it at: {saved_fname}
# '''

## task_name ='Kennedy_Space_Center_Visitor_Complex'
# saved_fname = r'E:\OneDrive_PSU\OneDrive - The Pennsylvania State University\Research_doc\LLM-Find\Downloaded_Data\Kennedy_Space_Center_Visitor_Complex_image.tif'
# task = rf'''1. Download the Kennedy Space Center Visitor Complex satellite image at level 18.
# 2. Save the downloaded data in tiff format, save it at: {saved_fname}
# '''

## task_name ='Hoover_Dam'
# saved_fname = r'E:\OneDrive_PSU\OneDrive - The Pennsylvania State University\Research_doc\LLM-Find\Downloaded_Data\Hoover_Dam_image.tif'
# task = rf'''1. Download the Hoover Dam satellite image at level 18.
# 2. Save the downloaded data in tiff format, save it at: {saved_fname}
# '''

## task_name ='Nigeria'
# saved_fname = r'E:\OneDrive_PSU\OneDrive - The Pennsylvania State University\Research_doc\LLM-Find\Downloaded_Data\Nigeria_image.tif'
# task = rf'''1. Download the Nigeria satellite image at level 8.
# 2. Save the downloaded data in tiff format, save it at: {saved_fname}
# '''

## task_name ='Afghanistan'
# saved_fname = r'E:\OneDrive_PSU\OneDrive - The Pennsylvania State University\Research_doc\LLM-Find\Downloaded_Data\Afghanistan_image.tif'
# task = rf'''1. Download the Afghanistan satellite image at level 8.
# 2. Save the downloaded data in tiff format, save it at: {saved_fname}
# '''

## task_name ='State_college'
# saved_fname = r'E:\OneDrive_PSU\OneDrive - The Pennsylvania State University\Research_doc\LLM-Find\Downloaded_Data\State_college_image.tif'
# task = rf'''1. Download the State College City, PA satellite image at level 12.
# 2. Save the downloaded data in tiff format, save it at: {saved_fname}
# '''

# #task_name = 'Tigard'
# saved_fname = r'E:\OneDrive_PSU\OneDrive - The Pennsylvania State University\Research_doc\LLM-Find\Downloaded_Data\Tigard_OR_image.tif'
# task = rf'''1. Download the Tigard, OR satellite image at level 14.
# 2. Save the downloaded data in tiff format, save it at: {saved_fname}
# '''

## task_name = "Xiong'an"
# downloaded_file_name = r'Xiong_an.tif'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download the Xiong'an New Area, China satellite image at level 12.
# 2. Save the downloaded data in tiff format, save it at: {saved_fname}
# '''

## task_name = "Penn_State_University"
# downloaded_file_name = r'Penn_State_University.tif'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download the Pennsylvania State University satellite image at level 15.
# 2. Save the downloaded data in tiff format, save it at: {saved_fname}
# '''


#________________________________Data source 7:  OpenTopography_____________________________
## task_name = "Wuhan_DEM"
# downloaded_file_name = r'Wuhan_DEM.tif'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download the 90m resolution DEM of Wuhan, China from SRTMGL3.
# 2. Save the downloaded data in tiff format, save it at: {saved_fname}
# '''

# # task_name = "Chongqing_DEM"
# downloaded_file_name = r'Chongqing_DEM.tif'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download the 30m resolution DEM of Chongqing, China from SRTMGL1.
# 2. Save the downloaded data in tiff format, save it at: {saved_fname}
# '''

# # task_name = "Hawaii_DEM"
# downloaded_file_name = r'Hawaii_DEM.tif'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download the 90m resolution DEM of Hawaii, USA from SRTMGL3.
# 2. Save the downloaded data in tiff format, save it at: {saved_fname}
# '''


## task_name = "Lhasa, China_DEM"
# downloaded_file_name = r'Lhasa_DEM.tif'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download the 30m resolution DEM of Lhasa, China, from COP30.
# 2. Save the downloaded data in tiff format, save it at: {saved_fname}
# '''


# # task_name = "Iceland"
# downloaded_file_name = r'Iceland_DEM.tif'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download the 30m resolution DEM of Iceland_DEM from EU_DTM.
# 2. Save the downloaded data in tiff format, save it at: {saved_fname}
# '''

## task_name = "Mount Everest"
# downloaded_file_name = r'Everest_DEM.tif'
# saved_fname = os.path.join(os.getcwd(), "Downloaded_Data", downloaded_file_name)
# task = rf'''1. Download the 30m resolution DEM of this region [south:27.82, west:86.73, north:28.17, east:87.13] from AW3D30.
# 2. Save the downloaded data in tiff format, save it at: {saved_fname}
# '''





def main(task, saved_fname, model_name):
    filename_only = os.path.basename(saved_fname)
    # Convert the data locations string back to a list if needed
    #saved_fname = saved_fname.split(';')  # Assuming data locations are joined by a semicolon
    #task_name = task_name
    #task = task
    return filename_only



if __name__ == "__main__":

    task = sys.argv[1]
    saved_fname = sys.argv[2]
    model_name = sys.argv[3]
    main(task, saved_fname, model_name)
downloaded_file_name = main(task, saved_fname, model_name)

#%%
#Create the model
if os.path.exists(saved_fname):
    os.remove(saved_fname)

save_dir = os.path.join(os.getcwd(), "Downloaded_Data")
os.makedirs(save_dir, exist_ok=True)

# model_name = r'gpt-4o'
OpenAI_key = helper.load_OpenAI_key()
model = ChatOpenAI(api_key=OpenAI_key, model=model_name, temperature=1)
#%%
#Select the data source
source_select_prompt_str = helper.create_select_prompt(task=task)

print(source_select_prompt_str)
#%%
#Pick up the data source handbook
from IPython.display import clear_output

async def fetch_chunks(model, source_select_prompt_str):
    chunks = []
    async for chunk in model.astream(source_select_prompt_str):
        chunks.append(chunk)
        # print(chunk.content, end="", flush=True)
    return chunks
nest_asyncio.apply()
chunks = asyncio.run(fetch_chunks(model, source_select_prompt_str))

clear_output(wait=True)
# clear_output(wait=False)
LLM_reply_str = helper.convert_chunks_to_str(chunks=chunks)

print("Select the data source: \n")
print(LLM_reply_str)
#%%
#Generate the data fetching program
import ast
select_source = ast.literal_eval(LLM_reply_str)

selected_data_source = select_source['Selected data source']
data_source_ID = constants.data_source_dict[selected_data_source]['ID']

print("selected_data_source:", selected_data_source)
print("data_source_ID:", data_source_ID)

handbook_list = constants.handbooks[f"{data_source_ID}"]
handbook_str =  '\n'.join([f"{idx + 1}. {line}" for idx, line in enumerate(handbook_list)])
print()
print(f"Handbook:\n{handbook_str}")
#%%
download_prompt_str = helper.create_download_prompt(task,saved_fname, selected_data_source, handbook_str)
print(download_prompt_str)
#%%
from IPython.display import clear_output
async def fetch_download_str(model, download_prompt_str):
    chunks = []
    async for chunk in model.astream(download_prompt_str):
        chunks.append(chunk)
        # print(chunk.content, end="", flush=True)
    return chunks
nest_asyncio.apply()
chunks = asyncio.run(fetch_chunks(model, download_prompt_str))
clear_output(wait=True)
# clear_output(wait=False)
LLM_reply_str = helper.convert_chunks_to_str(chunks=chunks)
print(LLM_reply_str)

#%%
code = helper.extract_code_from_str(LLM_reply_str, task)
display(Code(code, language='python'))
#%%
#Execute the generated program
code = code.replace('area({osm_id})->.searchArea;',
                    'relation({osm_id}); map_to_area->.searchArea;')  # GPT-4o never follow the related instruction!
code = helper.execute_complete_program(code=code, try_cnt=10, task=task, model_name=model_name,
                                       handbook_str=handbook_str)
code = code.replace('area({osm_id})->.searchArea;',
                    'relation({osm_id}); map_to_area->.searchArea;')  # GPT-4o never follow the related instruction!
display(Code(code, language='python'))
#%%


# Displaying the result in QGIS
if saved_fname.endswith('.gpkg') or saved_fname.endswith('.csv') or saved_fname.endswith('.shp'):
    layer = QgsVectorLayer(saved_fname, f"{downloaded_file_name}", "ogr")
    QgsProject.instance().addMapLayer(layer)
    print("vector data loaded")
elif saved_fname.endswith('.tif'):
    layer =QgsRasterLayer(saved_fname,f"{downloaded_file_name}")
    QgsProject.instance().addMapLayer(layer)
    print("Raster data loaded")

else:
    print("Unsupported file format")

print("SAVED FNAME: ",saved_fname)
# print("Layer path: ",layer_path)
