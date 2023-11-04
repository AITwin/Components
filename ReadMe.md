<img src="https://avatars.githubusercontent.com/u/125973400?s=150&v=4" alt="Logo de MobilityTwin.Brussels" height=150>

# Components

## Overview

This project implements all the components of the MobilityTwin.Brussels
data processing pipeline. It is designed to be flexible and configurable,
allowing you to easily add or remove components as needed.

## Some terminology

### Collector

A collector is a component that gathers data from one (in general) or more
external sources and stores it in a structured manner without (ideally) any processing
in the database. It can then be retrieved by other components for further processing or
directly by the end user. Collectors are made to run on a schedule.

### Harvester

A harvester is a component that processes raw data retrieved from collectors / harvesters
and applies necessary transformations before saving it to the database. In general,
harvesters are made to run on a schedule/follow a source collector/harvester schedule.

### Handler

A handler is a component that retrieves data from collectors and harvesters
and processes it in some way. In opposition to harvesters, handlers do
not save the data to the database. They are made to run on-demand.

## How it works

The project is built around the concept of components. Each component is a Python module that implements a specific
functionality. The components are grouped into three categories: handlers, collectors, and harvesters. Each component is
responsible for a specific task, such as retrieving data from a source, processing data, or saving data to the database.

The logic for each component is implemented in a separate Python module. The modules are stored in the `components`
directory. The `main.py` script is responsible for running the components and scheduling them.

To lighten the components, configuration files defining many properties of the components are stored in
the `configuration` directory. The configuration files are written in TOML format. The framework
will automatically load the configuration files for the components that are run and inject them into the components.

SQLAlchemy is used to interact with the database. It should not be used directly in the components. Instead, the
different helper functions defined in the `src.data` module should be used.

## Prerequisites

Before running the project, ensure the following:

Python is installed (preferably Python 3.11 or higher).
Required packages are installed. You can install them using pip:

`pip install -r requirements.txt`

## Usage

Clone the repository and navigate to the project directory.

Create a .env file in the project root directory and set the required environment variables. (See the .env.example file
for an example.)

Run specific handlers:

`python main.py --handlers handler_name1 handler_name2`

Run all handlers on a specific host and port and allowed hosts:

`python main.py --handlers * --host 192.12.12.1 --port 5242 --allowed-hosts localhost`

Run specific collectors:

`python main.py --collectors collector_name1 collector_name2`

Run specific harvesters:

`python main.py --harvesters harvester_name1 harvester_name2`

Run all handlers, collectors, and harvesters:

`python main.py --handlers * --collectors * --harvesters *`

Run collectors or harvesters once and exit (without scheduling):

`python main.py --collectors collector_name --now`

The script will start processing the data based on your input and configuration. Monitor the terminal for logs and
output.

## Configuration

Each component can be configured in the TOML files in the configuration directory. The configuration files are named
after the data provider they configure. For example, the configuration for the `stib_gtfs` handler is stored in
`config/stib.toml`.

## Contributing

We welcome contributions from the community to improve and enhance the MobilityTwin.Brussels project. Whether you are interested in fixing bugs, adding new features, or improving documentation, your help is valuable. 

You can learn more about how to contribute by reading the Contribute.md file.
