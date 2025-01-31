import openai
import csv
import uuid
import re
import os
import ast
import google.generativeai as genai
import pandas as pd
import json
import math
import random
from flask import session
from flask import jsonify



# Helper functions for determining node attributes
def determine_element_type(new_item_tag):
    """Determine the type of element based on the item tag."""
    new_item_tag = new_item_tag.upper()
    if 'VES' in new_item_tag or 'MP' in new_item_tag:
        return 'Equipment'
    elif new_item_tag.startswith('N'):
        return 'Nozzle'
    elif 'PI' in new_item_tag or 'PG' in new_item_tag:
        return 'Pressure Guage'
    elif 'COO' in new_item_tag or 'COOLER' in new_item_tag:
        return 'Cooler'
    elif new_item_tag.startswith('P') or 'PUMP' in new_item_tag:
        return 'Pump'
    elif new_item_tag.startswith('V'):
        return 'Valve'
    elif new_item_tag.startswith('H'):
        return 'Heat Exchanger'
    elif new_item_tag.startswith('F'):
        return 'Filter'
    elif new_item_tag.startswith('S'):
        return 'Sensor'
    elif new_item_tag.isdigit():
        return 'Piping Component'
    elif new_item_tag.startswith('J'):
        return 'Junction'
    else:
        return 'Instrument'


def determine_tag_prefix(new_item_tag):
    """Determine the tag prefix based on the item tag."""
    match = re.match(r"^[A-Za-z]+", new_item_tag)
    if match:
        return match.group(0)
    elif new_item_tag.isdigit():
        return 'PC'  # Piping Component
    return ""
def determine_tag_suffix(new_item_tag):
    """Determine the tag suffix based on the item tag."""
    # Check if the last character is alphabetical
    if re.search(r"[A-Za-z]$", new_item_tag):
        return new_item_tag[-1]  # Return the last character if it's a letter
    return " "

def get_measured_variable_code(new_item_tag):
    """Extract the MeasuredVariableCode (first character of the tag prefix)."""
    prefix = determine_tag_prefix(new_item_tag)
    if prefix:
        return prefix[0]  # First character of the prefix as MeasuredVariableCode
    return ""  # Return empty if no valid prefix is found

def get_instrument_type_modifier(new_item_tag):
    """Extract the InstrumentTypeModifier (remaining characters of the tag prefix)."""
    prefix = determine_tag_prefix(new_item_tag)
    if prefix:
        return prefix[1:]  # Remaining part of the prefix as InstrumentTypeModifier
    return ""  # Return empty if no valid prefix is found

def determine_tag_sequence_no(new_item_tag):
    """Determine the tag sequence number based on any digit in the item tag."""
    digits = re.findall(r"\d+", new_item_tag)  # Find all sequences of digits
    if digits:
        return digits[-1]  # Use the last found digit sequence
    return ""


def get_node_types(node_id1, node_id2, nodes_csv='uploaded_files/csvs_nodes.csv'):
    """
    Retrieve the types of two nodes from the nodes CSV file based on their IDs.

    :param node_id1: ID of the first node.
    :param node_id2: ID of the second node.
    :param nodes_csv: Path to the nodes CSV file.
    :return: A tuple containing the types of the two nodes (type1, type2). If a node is not found, 'Unknown' is returned for its type.
    """
    node_types = {'Unknown': 'Unknown'}
    try:
        with open(nodes_csv, mode='r') as file:
            reader = csv.reader(file)
            next(reader)  # Skip header row
            for row in reader:
                if len(row) < 2:  # Ensure the row has enough columns
                    continue
                node_id = row[0]
                element_type = row[1]
                if node_id == node_id1:
                    node_types['Node1'] = element_type
                elif node_id == node_id2:
                    node_types['Node2'] = element_type
                if 'Node1' in node_types and 'Node2' in node_types:
                    break
    except FileNotFoundError:
        print(f"File {nodes_csv} not found.")
        return 'Unknown', 'Unknown'

    # Get the types for the node IDs or default to 'Unknown'
    type1 = node_types.get('Node1', 'Unknown')
    type2 = node_types.get('Node2', 'Unknown')
    return type1, type2

# Function to generate a unique node ID with the 'GENAINODE' prefix
def generate_unique_node_id():
    """Generates a unique node ID using UUID."""
    return f"GENAINODE-{uuid.uuid4()}"

def determine_edge_type(element1, element2):
    """Determines the edge type between two elements based on predefined rules."""
    # Define the edge type rules
    edge_rules = {
        ('instrument', 'instrument'): 'Signal',
        ('instrument', 'junction'): 'Piping',
        ('instrument', 'nozzle'): 'Signal',
        ('instrument', 'piping component'): 'Piping',
        ('junction', 'instrument'): 'ConnectToProcess',
        ('junction', 'junction'): 'Piping',
        ('junction', 'opc'): 'Piping',
        ('junction', 'piping component'): 'Piping',
        ('junction', 'unknown'): 'Piping',
        ('nozzle', 'equipment'): 'DirectConnection',  # Rule for nozzle and equipment
        ('nozzle', 'instrument'): 'Signal',
        ('nozzle', 'nozzle'): 'Signal',
        ('nozzle', 'piping component'): 'Piping',
        ('opc', 'junction'): 'Piping',
        ('piping component', 'instrument'): 'Piping',
        ('piping component', 'junction'): 'Piping',
        ('piping component', 'nozzle'): 'Piping',
        ('piping component', 'opc'): 'Piping',
        ('piping component', 'piping component'): 'Piping',
        ('pump', 'valve'): 'Piping',
        ('pump', 'cooler'): 'Piping',
        ('cooler', 'valve'): 'Direct connection',
    }

    # Normalize the input order and convert to lowercase, removing spaces
    element1 = element1.strip().lower()
    element2 = element2.strip().lower()

    # Debugging: print inputs and normalized key
    #print(f"element1: '{element1}', element2: '{element2}'")  # Debugging line

    # Create normalized key by sorting elements
    normalized_key = tuple(sorted([element1, element2]))

    # Debugging: print the normalized key
    #print(f"Normalized Key: {normalized_key}")  # Debugging line

    # Get the edge type based on the rules
    edge_type = edge_rules.get(normalized_key, 'Piping')

    # Debugging: print the result
    #print(f"Edge Type: {edge_type}")  # Debugging line

    return edge_type

def get_edge_type_between_nodes(node_id1, node_id2, nodes_csv='uploaded_files/csvs_nodes.csv'):
    """
    Determines the edge type between two nodes by retrieving their types from the CSV
    and using the determine_edge_type function.

    :param node_id1: ID of the first node.
    :param node_id2: ID of the second node.
    :param nodes_csv: Path to the nodes CSV file.
    :return: The edge type between the two nodes.
    """
    # Retrieve the types of the two nodes
    type1, type2 = get_node_types(node_id1, node_id2, nodes_csv)
    
    # Determine the edge type based on the rules
    return determine_edge_type(type1, type2)

# Function to find the existing element in nodes.csv and derive the coordinates
def find_existing_element(existing_item_tag, nodes_csv):
    """Finds an existing element in the nodes CSV based on the given item tag."""
    # with open(nodes_csv, 'r') as csvfile:
    #     reader = csv.DictReader(csvfile)
    with open(nodes_csv, mode='r') as nodes_file:
        reader = csv.DictReader(nodes_file)
        first_column_name = reader.fieldnames[0]
        
        for row in reader:
             # Convert both ItemTag and existing_item_tag to lowercase for case-insensitive comparison
            if row['ItemTag'].lower() == existing_item_tag.lower():
                return {
                    'x': float(row['XCoordinate']),
                    'y': float(row['YCoordinate']),
                    'drawing_id': row['DrawingID'],
                    'id':row[first_column_name]
                }
    return None

new_nodes = []
new_nodes_sub=[]
#Function to calculate coord sub
def calculate_new_coordinates_sub(existing_element, nodes_csv, new_nodes_sub, initial_radius=0.01, radius_increment=0.01, max_radius=0.3):
    """Calculates new coordinates for a new node based on the existing node's position."""
    existing_x = float(existing_element['x'])
    existing_y = float(existing_element['y'])
    radius = initial_radius
    angle_increment = math.pi / 6

    while radius <= max_radius:
        for i in range(12):
            angle = i * angle_increment
            x_new = existing_x + radius * math.cos(angle)
            y_new = existing_y + radius * math.sin(angle)

            if is_space_available_sub(x_new, y_new, nodes_csv, new_nodes_sub):
                new_nodes_sub.append((x_new, y_new))  # Track new nodes to avoid overlap in subsequent calls
                return x_new, y_new

        radius += radius_increment

    raise ValueError("No available space found near the existing element.")

def is_space_available_sub(x_new, y_new, nodes_csv, new_nodes_sub, threshold=0.05):
    """Checks if there is enough space to place a new node at the given coordinates."""
    # Check against existing nodes from the CSV file
    with open(nodes_csv, 'r') as csvfile:
        reader = csv.reader(csvfile)
        next(reader)
        for row in reader:
            if len(row) > 3 and row[2] and row[3]:
                try:
                    existing_x = float(row[2])
                    existing_y = float(row[3])
                    if math.sqrt((existing_x - x_new) ** 2 + (existing_y - y_new) ** 2) < threshold:
                        return False
                except ValueError:
                    continue

    # Check against newly added nodes to prevent overlap
    for (existing_x, existing_y) in new_nodes_sub:
        if math.sqrt((existing_x - x_new) ** 2 + (existing_y - y_new) ** 2) < threshold:
            return False

    return True


def get_connected_nodes(node_id, edges_csv):
    """
    Retrieves a list of nodes connected to the given node ID.

    Args:
        node_id (str): The ID of the node to find connections for.
        edges_csv (str): Path to the edges CSV file.

    Returns:
        list: A list of connected node IDs.
    """
    connected_nodes = []
    try:
        with open(edges_csv, 'r', encoding='UTF-8') as csvfile:
            reader = csv.reader(csvfile)
            next(reader)  # Skip header
            for row in reader:
                if len(row) >= 2:  # Ensure row has enough columns
                    if row[0] == node_id or row[1] == node_id:
                        connected_nodes.append(row[1] if row[0] == node_id else row[0])
    except FileNotFoundError:
        raise FileNotFoundError(f"Edges CSV file '{edges_csv}' not found.")
    return connected_nodes


def get_node_coordinates(node_ids, nodes_csv):
    """Retrieves the coordinates of nodes based on the provided node IDs"""
    coordinates = []
    try:
        with open(nodes_csv, 'r') as csvfile:
            reader = csv.reader(csvfile)
            next(reader)  # Skip header
            for row in reader:
                if len(row) >= 4 and row[0] in node_ids:
                    try:
                        x = float(row[2])
                        y = float(row[3])
                        coordinates.append((x, y))
                    except ValueError:
                        print(f"Skipping invalid coordinates in row: {row}")
    except FileNotFoundError:
        raise FileNotFoundError(f"Nodes CSV file '{nodes_csv}' not found.")
    return coordinates


def is_space_available(x_new, y_new, nodes_csv, new_nodes, connected_coordinates, threshold=0.05):
    """Checks if there is enough space to place a new node at the given coordinates."""
    # Check existing nodes in CSV
    try:
        with open(nodes_csv, 'r') as csvfile:
            reader = csv.reader(csvfile)
            next(reader)
            for row in reader:
                if len(row) >= 4 and row[2] and row[3]:
                    try:
                        existing_x = float(row[2])
                        existing_y = float(row[3])
                        if math.sqrt((existing_x - x_new) ** 2 + (existing_y - y_new) ** 2) < threshold:
                            return False
                    except ValueError:
                        continue
    except FileNotFoundError:
        raise FileNotFoundError(f"Nodes CSV file '{nodes_csv}' not found.")

    # Check newly added nodes
    for (existing_x, existing_y) in new_nodes:
        if math.sqrt((existing_x - x_new) ** 2 + (existing_y - y_new) ** 2) < threshold:
            return False

    # Check connected nodes to avoid overlapping with them
    for connected_x, connected_y in connected_coordinates:
        if math.sqrt((connected_x - x_new) ** 2 + (connected_y - y_new) ** 2) < threshold:
            return False

    return True


def calculate_new_coordinates(existing_element, nodes_csv, edges_csv, new_nodes, initial_radius=0.05, radius_increment=0.05, max_radius=0.5):
    """Calculates new coordinates for a new node based on the existing node's position."""
    try:
        existing_x = float(existing_element['x'])
        existing_y = float(existing_element['y'])
    except (KeyError, ValueError) as e:
        raise ValueError(f"Invalid 'existing_element': {existing_element}. Error: {e}")

    radius = initial_radius
    angle_increment = math.pi / 6  # 30 degrees

    # Find connected nodes
    connected_node_ids = get_connected_nodes(existing_element['id'], edges_csv)
    connected_coordinates = get_node_coordinates(connected_node_ids, nodes_csv)

    while radius <= max_radius:
        for i in range(12):  # Try 12 points on the current circle
            angle = i * angle_increment
            x_new = existing_x + radius * math.cos(angle)
            y_new = existing_y + radius * math.sin(angle)

            # Add an offset to avoid same X or Y placement
            x_new += 0.01 * i  # Small incremental offset
            y_new += 0.01 * i

            if is_space_available(x_new, y_new, nodes_csv, new_nodes, connected_coordinates):
                # Ensure the new node doesn't align too closely with existing ones
                for (connected_x, connected_y) in connected_coordinates:
                    if abs(connected_x - x_new) < 0.05 or abs(connected_y - y_new) < 0.05:
                        continue  # Skip this placement

                # If everything checks out, add the node
                new_nodes.append((x_new, y_new))
                return x_new, y_new

        radius += radius_increment  # Increase radius if no valid point is found

    raise ValueError("No available space found near the existing element.")

def check_existing_edge(node1_id, node2_id, edges_csv):
    """
    Checks if an edge exists between two nodes in the provided edges CSV file.

    Args:
        node1_id (str): The ID of the first node.
        node2_id (str): The ID of the second node.
        edges_csv (str): Path to the edges CSV file with 'StartNode' and 'EndNode' columns.

    Returns:
        bool: True if an edge exists between the two nodes (in either direction), False otherwise.
    """
    # Read all edges from edges.csv
    with open(edges_csv, mode='r') as csvfile:
        edges = list(csv.DictReader(csvfile))
    
    # Check if an edge exists between the two nodes
    for edge in edges:
        if (edge['StartNode'] == node1_id and edge['EndNode'] == node2_id) or (edge['StartNode'] == node2_id and edge['EndNode'] == node1_id):
            return True
    return False

def remove_existing_edge(node1_id, node2_id, edges_csv):
    """
    Removes an edge between two nodes from the provided edges CSV file if it exists.

    Args:
        node1_id (str): The ID of the first node.
        node2_id (str): The ID of the second node.
        edges_csv (str): Path to the edges CSV file with 'StartNode' and 'EndNode' columns.

    Returns:
        The function modifies the CSV file by removing the edge between the two nodes if found.
    """
    # Read all edges from edges.csv
    with open(edges_csv, mode='r') as csvfile:
        edges = list(csv.DictReader(csvfile))
    
    # Find and remove the edge between the two nodes if it exists
    edge_to_remove = None
    for edge in edges:
        if (edge['StartNode'] == node1_id and edge['EndNode'] == node2_id) or (edge['StartNode'] == node2_id and edge['EndNode'] == node1_id):
            edge_to_remove = edge
            break
    
    if edge_to_remove:
        edges.remove(edge_to_remove)
        # Write the updated edges back to edges.csv
        with open(edges_csv, mode='w', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=edge_to_remove.keys())
            writer.writeheader()
            writer.writerows(edges)
        #print(f"Removed existing edge between {node1_id} and {node2_id}")

# Function to add the new node to the nodes.csv
def add_bw_node(new_item_tag, nodes_csv, node1_item_tag, node2_item_tag, edges_csv):
    """
    Adds a new node that acts as a 'bridge' between two existing nodes, creating an edge between them.

    Args:
        new_item_tag (str): The item tag of the new node to be added.
        nodes_csv (str): Path to the nodes CSV file.
        node1_item_tag (str): The item tag of the first existing node.
        node2_item_tag (str): The item tag of the second existing node.
        edges_csv (str): Path to the edges CSV file."""
     
    existing_element1 = find_existing_element(node1_item_tag, nodes_csv)
    
    if not existing_element1:
        #print(f"Error: Element with item tag {node1_item_tag} not found.")
        return {'status': 'error', 'message': f'Element with item tag {node1_item_tag} not found.'}
    
    existing_element2 = find_existing_element(node2_item_tag, nodes_csv)
    
    if not existing_element2:
        return {'status': 'error', 'message': f'Element with item tag {node2_item_tag} not found.'}
        # print(f"Error: Element with item tag {node2_item_tag} not found.")
        # return
    
    new_exists = find_existing_element(new_item_tag, nodes_csv)
    
    if new_exists:
        return {'status': 'error', 'message': f'Element with item tag {new_item_tag} already exists.'}
        # print(f"Error: Element with item tag {new_item_tag} already exists.")
        # return

    
    node_ids = read_node_ids(nodes_csv)  # Read node IDs from the nodes file

    node1_id = node_ids.get(node1_item_tag, None)  # Get node ID for existing_item_tag
    node2_id = node_ids.get(node2_item_tag, None) 

    if check_existing_edge(node1_id, node2_id, edges_csv):
        # Remove the existing edge if it exists
        remove_existing_edge(node1_id, node2_id, edges_csv)

    new_node_id = generate_unique_node_id()
    element_type = determine_element_type(new_item_tag)
    tag_prefix = determine_tag_prefix(new_item_tag)
    tag_suffix= determine_tag_suffix(new_item_tag)
    tag_measuredVariable = get_measured_variable_code(new_item_tag)
    tag_InstrumentTypeModifier = get_instrument_type_modifier(new_item_tag)
    tag_sequence_no = determine_tag_sequence_no(new_item_tag)
    x_new = (existing_element1['x'] + existing_element2['x']) / 2
    y_new = (existing_element1['y'] + existing_element2['y']) / 2
    drawing_id = existing_element1['drawing_id']

    # Define the empty fields (subtype, tag suffix, etc.)
    empty_field = ""

    # Append the new node data to the nodes.csv
    with open(nodes_csv, 'a', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([
            new_node_id, element_type, x_new, y_new, drawing_id,
            empty_field, new_item_tag, tag_prefix, tag_sequence_no,
            tag_suffix, tag_measuredVariable, tag_InstrumentTypeModifier, empty_field,
            empty_field, empty_field
        ])
    return {'status':'success','message':'added bw elements'}
    #print(f"New element added: {new_node_id}, {element_type}, {tag_prefix}-{tag_sequence_no}, x: {x_new}, y: {y_new}, drawing_id: {drawing_id}")


def add_edges(new_item_tag, existing_item_tag, nodes_file_path, edges_file_path):
    """
    Adds a new edge between two nodes in the system by updating the edges CSV file.

    This function creates a new edge between the `new_item_tag` and `existing_item_tag` by:
    1. Retrieving their respective node IDs from the `nodes_file_path` (nodes CSV).
    2. Generating a unique edge ID and run ID.
    3. Finding the drawing ID of the existing node.
    4. Appending the new edge to the `edges_file_path` (edges CSV).

    Args:
        new_item_tag (str): The item tag of the new node to be connected.
        existing_item_tag (str): The item tag of the existing node to connect to.
        nodes_file_path (str): The file path to the nodes CSV.
        edges_file_path (str): The file path to the edges CSV.

    Returns:
        None: If the edge is successfully added, the function completes without returning anything. 
              Prints an error message if the node IDs are not found.
    """
    node_ids = read_node_ids(nodes_file_path)  # Read node IDs from the nodes file

    start_node_id = node_ids.get(existing_item_tag, None)  # Get node ID for existing_item_tag
    end_node_id = node_ids.get(new_item_tag, None)         # Get node ID for new_item_tag

    if start_node_id and end_node_id:
        edge_id = f"GENAIEDGE-{uuid.uuid4()}"  # Generate a unique ID for the edge
        run_id = str(uuid.uuid4()).replace('-', '').upper()
        with open(nodes_file_path, mode='r') as nodes_file:
            nodes_reader = csv.DictReader(nodes_file)
            existing_node = next((node for node in nodes_reader if node['ItemTag'] == existing_item_tag), None)
            drawing_id = existing_node['DrawingID'] if existing_node else ''

        # Open the edges file to append the new edge
        with open(edges_file_path, mode='r') as edges_file:
            edges_reader = csv.DictReader(edges_file)
            fieldnames = edges_reader.fieldnames

        # Append the new edge to the edges file
        with open(edges_file_path, mode='a', newline='') as edges_file:
            edges_writer = csv.DictWriter(edges_file, fieldnames=fieldnames)

            new_edge = {field: '' for field in fieldnames}  # Start with empty strings for all fields

            if fieldnames[0]:
                new_edge[fieldnames[0]] = edge_id
            if 'Type' in fieldnames:
                new_edge['Type'] = 'Direct Connection'
            if 'RunID' in fieldnames:
                new_edge['RunID']=run_id
            if 'StartNode' in fieldnames:
                new_edge['StartNode'] = start_node_id
            if 'EndNode' in fieldnames:
                new_edge['EndNode'] = end_node_id
            if 'FlowDir' in fieldnames:
                new_edge['FlowDir'] = 'StartNode to EndNode'
            if 'DrawingID' in fieldnames:
                new_edge['DrawingID'] = drawing_id

            # Write the new edge to the CSV
            edges_writer.writerow(new_edge)

    else:
        print("Error: Could not find node IDs for the given tags.")

# Function to add the new node to the nodes.csv
def add_new_node(new_item_tag, nodes_csv, edges_csv, existing_item_tag, offset=(0.05, 0.05)):
    """
    Adds a new node to the nodes CSV file by calculating its position relative to an existing node.

    This function:
    1. Checks if the `existing_item_tag` and `new_item_tag` are valid (i.e., the existing item exists, 
       and the new item does not already exist).
    2. Generates a unique ID for the new node and calculates its position relative to the existing node.
    3. Adds the new node to the `nodes_csv` file with relevant attributes such as `element_type`, 
       `drawing_id`, `coordinates`, etc.

    Args:
        new_item_tag (str): The item tag of the new node to be added.
        nodes_csv (str): Path to the CSV file containing existing nodes.
        edges_csv (str): Path to the CSV file containing edges (not used in this function, but can be extended).
        existing_item_tag (str): The item tag of an existing node to determine the new node's position."""
    # Check if the existing_item_tag exists in the nodes.csv
    existing_element = find_existing_element(existing_item_tag, nodes_csv)
    
    # Check if the new_item_tag already exists in the nodes.csv
    new_exists = find_existing_element(new_item_tag, nodes_csv)
    
    if not existing_element:
        #print(f"Error: Element with item tag {existing_item_tag} not found.")
        return {'status': 'error', 'message': f'element with item tag {existing_item_tag} not found.'}
        #return
    
    if new_exists:
        #print(f"Error: Element with item tag {new_item_tag} already exists.")
        return {'status': 'error', 'message': f'Element with item tag {new_item_tag} already exists.'}
        #return

    new_node_id = generate_unique_node_id()
    element_type = determine_element_type(new_item_tag)
    tag_prefix = determine_tag_prefix(new_item_tag)
    tag_sequence_no = determine_tag_sequence_no(new_item_tag)
    x_new, y_new = calculate_new_coordinates(existing_element, nodes_csv,edges_csv, new_nodes)
    drawing_id = existing_element['drawing_id']
    tag_suffix=determine_tag_suffix(new_item_tag)
    MeasuredVariableCode=get_measured_variable_code(new_item_tag)
    InstrumentTypeModifier=get_instrument_type_modifier(new_item_tag)


    # Define the empty fields (subtype, tag suffix, etc.)
    empty_field = ""

    # Append the new node data to the nodes.csv
    with open(nodes_csv, 'a', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([
            new_node_id, element_type, x_new, y_new, drawing_id,
            empty_field, new_item_tag, tag_prefix, tag_sequence_no,
            tag_suffix, MeasuredVariableCode, InstrumentTypeModifier, empty_field,
            empty_field, empty_field
        ])
    return {'status':'success','message':f"Added element:{new_item_tag}"}
    #print(f"New element added: {new_node_id}, {element_type}, {tag_prefix}-{tag_sequence_no}, x: {x_new}, y: {y_new}, drawing_id: {drawing_id}")

# Function to read node IDs from nodes.csv
def read_node_ids(file_path):
    """Read node IDs from the first column of the nodes.csv file."""
    node_ids = {}
    with open(file_path, mode='r') as nodes_file:
        nodes_reader = csv.DictReader(nodes_file)
        first_column_name = nodes_reader.fieldnames[0]  # Get the first column name
        for row in nodes_reader:
            item_tag = row['ItemTag']
            node_id = row[first_column_name]  # Use the first column as ID
            node_ids[item_tag] = node_id
    return node_ids

# Function to handle adding nodes from dict
def add_nodes_from_dict(add_dict, nodes_csv, edges_csv):
    """
    Adds nodes to the nodes CSV based on a dictionary of existing node tags and their new associated nodes.

    Args:
        add_dict (dict): A dictionary where keys are existing node tags and values are new node tags to be added.
        nodes_csv (str): Path to the CSV file containing existing nodes.
        edges_csv (str): Path to the CSV file containing edges (not used in this function, but can be extended).

    Returns:
        dict: A status message indicating success or failure.
    """
    with open(nodes_csv, mode='r') as nodes_file:
        nodes_reader = csv.DictReader(nodes_file)
        nodes_data = list(nodes_reader)
    first_column_name = nodes_reader.fieldnames[0] if nodes_reader.fieldnames else None
    nodes_changed = False
    

    for existing_node_tag, new_node_tags in add_dict.items():
        if not isinstance(new_node_tags, list):
            new_node_tags = [new_node_tags]
        existing_node = next((node for node in nodes_data if node['ItemTag'] == existing_node_tag), None)
        if not existing_node:
            return{'status':'error','message':f'The node with item tag {existing_node_tag} does not exist in the nodes file.'}
            #print(f"The node with item tag {existing_node_tag} does not exist in the nodes file.")
            continue
        for new_node_tag in new_node_tags:
            # Check if the new node already exists
            new_node = next((node for node in nodes_data if node['ItemTag'] == new_node_tag), None)
            if new_node:
                return {'status': 'error', 'message': f'The node with item tag {new_node_tag} already exists in the nodes file.'}
            #     # print(f"Error: The node with item tag {new_node_tag} already exists in the nodes file.")
            #     # continue
        for new_node_tag in new_node_tags:
            new_id = f"GENAINODE-{uuid.uuid4()}"
            type_of_element = determine_element_type(new_node_tag)
            tag_prefix = determine_tag_prefix(new_node_tag)
            tag_sequence_no = determine_tag_sequence_no(new_node_tag)
            tag_suffix= determine_tag_suffix(new_node_tag)
            tag_measuredVariable = get_measured_variable_code(new_node_tag)
            tag_InstrumentTypeModifier = get_instrument_type_modifier(new_node_tag)
            existing_element = find_existing_element(existing_node_tag, nodes_csv)
            #print(existing_element)
            #print(existing_node)
            x_coordinate, y_coordinate = calculate_new_coordinates(existing_element, nodes_csv,edges_csv,new_nodes)
            drawing_id = existing_node['DrawingID']
            new_node = {
                first_column_name: new_id,
                'Type': type_of_element,
                'XCoordinate': x_coordinate,
                'YCoordinate': y_coordinate,
                'DrawingID': drawing_id,
                'ItemTag': new_node_tag,
                'TagPrefix': tag_prefix,
                'TagSequenceNo': tag_sequence_no,
                'TagSuffix':tag_suffix,
                'MeasuredVariableCode': tag_measuredVariable,
                'InstrumentTypeModifier':tag_InstrumentTypeModifier
            }
            nodes_data.append(new_node)
            nodes_changed = True

    if nodes_changed:
        with open(nodes_csv, mode='w', newline='') as nodes_file:
            fieldnames = nodes_data[0].keys()
            writer = csv.DictWriter(nodes_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(nodes_data)
        return {'status':'success','message':'added nodes from dict'}
        #print("Nodes CSV file updated successfully!") 

def read_nodes(file_path):
    """Read nodes and return a dictionary of item tags mapped to node IDs."""
    nodes = {}
    with open(file_path, mode='r', encoding='utf-8-sig') as file:
        reader = csv.DictReader(file)
        for row in reader:
            #print(row.keys())
            nodes[row['ItemTag'].lower()] = row['ID']
    return nodes

def get_item_tag_from_node_id(node_id, nodes_file_path):
    """Get the item tag associated with a node ID."""
    with open(nodes_file_path, mode='r', encoding='utf-8-sig') as file:
        reader = csv.DictReader(file)
        for row in reader:
            if row['ID'] == node_id:
                return row['ItemTag']
    return None

def is_nozzle(node_id, nodes_file_path):
    """
    Check if the given node ID corresponds to a nozzle.
    
    Args:
        node_id (str): The ID of the node to check.
        nodes_file_path (str): Path to the CSV file containing node data.

    Returns:
        bool: True if the node is a nozzle, False otherwise.
    """
    with open(nodes_file_path, mode='r', encoding='utf-8-sig') as nodes_file:
        nodes = csv.DictReader(nodes_file)

        for node in nodes:
            if node['ID'] == node_id and node.get('Type', '').lower() == 'nozzle':
                return True

    return False

def is_leaf_node(node_id, edges):
    """Check if the node is a leaf node (no outgoing or incoming edges)."""
    for edge in edges:
        if edge['StartNode'] == node_id or edge['EndNode'] == node_id:
            return False
    return True

def remove_node_and_update_edges(item_tag, nodes_file_path, edges_file_path):
    """Remove a node and update edges accordingly using item tags."""
    # Step 1: Read nodes and edges from the files
    node_ids = read_nodes(nodes_file_path)

    # Step 2: Find the node ID associated with the item tag (case-insensitive comparison)
    node_id_to_remove = node_ids.get(item_tag.lower())  # Case-insensitive lookup in node_ids

    if not node_id_to_remove:
        return {'status': 'error', 'message': f'Node with item tag {item_tag} not found.'}
    
    node_tag_to_remove = get_item_tag_from_node_id(node_id_to_remove, nodes_file_path)

    if not node_tag_to_remove:
        return {'status': 'error', 'message': f'ItemTag for Node ID {node_id_to_remove} not found.'}

    with open(edges_file_path, mode='r', encoding='utf-8-sig') as edges_file:
        edges = list(csv.DictReader(edges_file))

    node_tag_to_remove = node_tag_to_remove.lower()  # Convert to uppercase for case-insensitive comparison

    # Step 2: Identify if the node is a vessel
    is_vessel = node_tag_to_remove.startswith("ves")  # Example condition for identifying vessels.

    # Step 3: Handle nozzles if the node is a vessel
    nozzles_to_remove = []
    nozzle_item_tags = []  # List to store item tags of nozzles to remove

    if is_vessel:
        for edge in edges:
            if edge['StartNode'] == node_id_to_remove and is_nozzle(edge['EndNode'], nodes_file_path):
                nozzles_to_remove.append(edge['EndNode'])
                item_tag = get_item_tag_from_node_id(edge['EndNode'], nodes_file_path)
                if item_tag:
                    nozzle_item_tags.append(item_tag)
            elif edge['EndNode'] == node_id_to_remove and is_nozzle(edge['StartNode'], nodes_file_path):
                nozzles_to_remove.append(edge['StartNode'])
                item_tag = get_item_tag_from_node_id(edge['StartNode'], nodes_file_path)
                if item_tag:
                    nozzle_item_tags.append(item_tag)

    # Read edges from the edges file
    with open(edges_file_path, mode='r') as edges_file:
        edges = list(csv.DictReader(edges_file))
    
    
    # Step 2: Check if it's a leaf node
    if is_leaf_node(node_id_to_remove, edges):
        # Remove the node if it's a leaf node
        with open(nodes_file_path, mode='r') as nodes_file:
            rows = list(csv.DictReader(nodes_file))
        with open(nodes_file_path, mode='w', newline='') as nodes_file:
            writer = csv.DictWriter(nodes_file, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(row for row in rows if row['ItemTag'].lower() != item_tag.lower())

        #print(f"Node {item_tag} is a leaf node and has been removed successfully!")
        return{'status':'success','message':'Deleted successfully'}

    # Step 3: Find all nodes connected to the node to be removed
    connected_nodes = []
    for edge in edges:
        if edge['StartNode'] == node_id_to_remove:
            connected_nodes.append(edge['EndNode'])
        elif edge['EndNode'] == node_id_to_remove:
            connected_nodes.append(edge['StartNode'])

    # Convert connected node IDs to item tags
    connected_item_tags = [get_item_tag_from_node_id(node_id, nodes_file_path) for node_id in connected_nodes]

    # Step 4: Remove the node from the nodes CSV
    with open(nodes_file_path, mode='r', encoding='utf-8-sig') as nodes_file:
        rows = list(csv.DictReader(nodes_file))

    # Create a set of all item tags to remove for efficient filtering
    item_tags_to_remove = set([item_tag.lower()] + [tag.lower() for tag in nozzle_item_tags])

    with open(nodes_file_path, mode='w', newline='', encoding='utf-8-sig') as nodes_file:
        writer = csv.DictWriter(nodes_file, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(row for row in rows if row['ItemTag'].lower() not in item_tags_to_remove)
    
    #print(f"Node {item_tag} removed successfully!")

    # Step 5: Remove edges related to the node from edges CSV
    remaining_edges = [edge for edge in edges if edge['StartNode'] != node_id_to_remove and edge['EndNode'] != node_id_to_remove]

    with open(edges_file_path, mode='w', newline='') as edges_file:
        writer = csv.DictWriter(edges_file, fieldnames=edges[0].keys())
        writer.writeheader()
        writer.writerows(remaining_edges)

    #print(f"Edges related to {item_tag} removed successfully!")

    # Step 6: Connect remaining nodes
    if connected_item_tags:
        start_item_tag = random.choice(connected_item_tags)  # Select a random item tag as the start node
        remaining_connected_item_tags = [tag for tag in connected_item_tags if tag.lower() != start_item_tag.lower()]

        # Debugging: Print the item tags of the nodes being connected
        #print(f"Connecting nodes: {start_item_tag} with {remaining_connected_item_tags}")

        for new_end_item_tag in remaining_connected_item_tags:
            add_edges(new_end_item_tag, start_item_tag, nodes_file_path, edges_file_path)

    #print(f"Updated edges after removing node {item_tag}.")
    return{'status':'success','message':'Deleted successfully'}
# Function to handle adding edges from dict
def add_edges_from_dict(add_dict, nodes_file_path, edges_file_path):
    """
    Adds edges to the edges CSV based on a dictionary of existing node tags and their new associated nodes.

    Args:
        add_dict (dict): A dictionary where keys are existing node tags and values are new node tags to which edges should be created.
        nodes_file_path (str): Path to the CSV file containing node information.
        edges_file_path (str): Path to the CSV file containing edges information.

    Returns:
        bool: True if edges were added or updated, False otherwise.
    """
    node_ids = read_node_ids(nodes_file_path)  # Retrieve node information
    edges_changed = False  # Initialize the flag to track if edges are changed

    with open(edges_file_path, mode='r') as edges_file:
        edges_reader = csv.DictReader(edges_file)
        fieldnames = edges_reader.fieldnames

    with open(edges_file_path, mode='a', newline='') as edges_file:
        edges_writer = csv.DictWriter(edges_file, fieldnames=fieldnames)
        for existing_node_tag, new_node_tags in add_dict.items():
            if not isinstance(new_node_tags, list):
                new_node_tags = [new_node_tags]
            start_node = node_ids.get(existing_node_tag, None)
            for new_node_tag in new_node_tags:
                end_node = node_ids.get(new_node_tag, None)
                if start_node and end_node:
                    edge_id = f"GENAIEDGE-{uuid.uuid4()}"
                    run_id = str(uuid.uuid4()).replace('-', '').upper()
                    new_edge = {
                        fieldnames[0]: edge_id,
                        'Type': 'Direct Connection',
                        'StartNode': start_node,
                        'RunID':run_id,
                        'EndNode': end_node,
                        'FlowDir': 'StartNode to EndNode',
                        'DrawingID': node_ids[existing_node_tag]  # Assuming you have DrawingID in node_ids
                    }
                    edges_writer.writerow(new_edge)
                    edges_changed = True  # Set the flag to True when an edge is added

    # if edges_changed:
    #     print("Edges CSV file updated successfully!")
    # else:
    #     print("No edges were added or changed.")

    return edges_changed  # Return the flag indicating whether edges were changed

import csv

def swap_node_info(element_1, element_2, nodes_csv):
    """
    Swaps all information except 'XCoordinate', 'YCoordinate', and the first column ('NodeID') 
    between two elements identified by their ItemTag in the nodes CSV file.

    :param element_1: ItemTag of the first element.
    :param element_2: ItemTag of the second element.
    :param nodes_csv: Path to the nodes CSV file.
    :return: Dictionary indicating success or error status.
    """
    rows = []
    element_1_data = None
    element_2_data = None
    node_id_field = None  # To track the first column's name

    # Read the CSV file and find the rows corresponding to the elements
    with open(nodes_csv, 'r') as csvfile:
        reader = csv.DictReader(csvfile)
        fieldnames = reader.fieldnames
        node_id_field = fieldnames[0]  # First column is NodeID

        for row in reader:
            if row['ItemTag'] == element_1:
                element_1_data = row
            elif row['ItemTag'] == element_2:
                element_2_data = row
            rows.append(row)

    # Check if both elements were found
    if element_1_data is None or element_2_data is None:
        return {'status': 'error', 'message': 'One or both elements not found in the CSV.'}

    # Swap the information (excluding specific fields)
    for field in fieldnames:
        if field not in ['XCoordinate', 'YCoordinate', node_id_field]:
            element_1_data[field], element_2_data[field] = element_2_data[field], element_1_data[field]

    # Write the updated rows back to the CSV
    with open(nodes_csv, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            # Update rows with swapped information
            if row['ItemTag'] == element_1:
                writer.writerow(element_1_data)
            elif row['ItemTag'] == element_2:
                writer.writerow(element_2_data)
            else:
                writer.writerow(row)

    return {'status': 'success', 'message': 'Information swapped successfully.'}

import csv

def update_item_types(csv_file, item_type_updates):
    """
    Updates the 'type' column in the CSV file based on the provided item_type_updates dictionary.
    Also appends 'TagPrefix' and 'SequenceNo' information for each updated item, and modifies 
    the 'NominalDiameter' if the dictionary contains item tags with new sizes.

    :param csv_file: Path to the CSV file.
    :param item_type_updates: Dictionary where keys are existing item tags. Values are either:
                              - New item tags (str) for updating the 'Type' column, or
                              - New sizes (int) to update 'NominalDiameter' if the value is a digit.
                              - A special case where {"operation": "type", <item_tag>: <new_type>}
                                updates the 'Type' column for the specified item tag.
    """
    updated_rows = []
    item_tags_found = []  # Track which item tags were found and updated

    # Check if the dictionary contains the special "operation": "type" case
    if "operation" in item_type_updates and item_type_updates["operation"] == "type":
        operation_type_updates = {k: v for k, v in item_type_updates.items() if k != "operation"}

        # Process the items under "operation: type"
        with open(csv_file, 'r', newline='') as file:
            reader = csv.DictReader(file)
            fieldnames = reader.fieldnames
            # Ensure 'NominalDiameter' column exists
            if 'NominalDiameter' not in fieldnames:
                fieldnames.append('NominalDiameter')

            for row in reader:
                item_tag = row['ItemTag']
                if item_tag in operation_type_updates:
                    # Update the 'Type' column for the item tag
                    row['Type'] = operation_type_updates[item_tag]
                    item_tags_found.append(item_tag)

                updated_rows.append(row)
    else:
        # Process regular updates for type, item tags, and sizes
        with open(csv_file, 'r', newline='') as file:
            reader = csv.DictReader(file)
            fieldnames = reader.fieldnames
            # Ensure 'NominalDiameter' column exists
            if 'NominalDiameter' not in fieldnames:
                fieldnames.append('NominalDiameter')

            for row in reader:
                item_tag = row['ItemTag']
                
                if item_tag in item_type_updates:
                    new_value = item_type_updates[item_tag]
                    
                    if isinstance(new_value, str):  # If the value is a string, assume it's a new item tag
                        row['Type'] = determine_element_type(new_value)
                        row['TagPrefix'] = determine_tag_prefix(new_value)
                        row['TagSequenceNo'] = determine_tag_sequence_no(new_value)
                        row['ItemTag'] = new_value  # Only update the item tag if the value is a new tag
                        row['TagSuffix'] = determine_tag_suffix(new_value)
                        row['MeasuredVariableCode'] = get_measured_variable_code(new_value)
                        row['InstrumentTypeModifier'] = get_instrument_type_modifier(new_value)
                    elif isinstance(new_value, (int, float)):  # If the value is a number, assume it's a new size
                        row['NominalDiameter'] = new_value  # Update the NominalDiameter column
                    
                    item_tags_found.append(item_tag)

                updated_rows.append(row)

    # If any item_tag was found and updated, write back to the CSV
    if item_tags_found:
        with open(csv_file, 'w', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(updated_rows)
        return {'status': 'success', 'message': 'Updated'}
    else:
        return {'status': 'error', 'message': 'Elements with given item tags not found'}

def count_row(file_path):
    # Load the existing CSV file
    df = pd.read_csv(file_path)
    # Store the initial row count in Flask's session
    session['initial_row_count'] = len(df)  
    #print(f"Updated initial_row_count: {session['initial_row_count']}")
    return session['initial_row_count']

class Node:
    def __init__(self, id, element_type, item_tag, x, y, drawing_id, tag_prefix, tag_sequence_no, tag_suffix,tag_measuredVariable,tag_InstrumentTypeModifier):
        self.id = id
        self.element_type = element_type
        self.item_tag = item_tag
        self.x = x
        self.y = y
        self.tag_prefix = tag_prefix
        self.tag_sequence_no = tag_sequence_no
        self.tag_suffix = tag_suffix
        self.tag_measuredVariable = tag_measuredVariable
        self.tag_InstrumentTypeModifier = tag_InstrumentTypeModifier
        self.drawing_id = drawing_id
        self.connections = []

    def add_connection(self, edge):
        self.connections.append(edge)


class Edge:
    def __init__(self, id, run_id,start_node, end_node,edge_type, flow_dir='StartNode to EndNode'):
        self.id = id
        self.run_id=run_id
        self.start_node = start_node
        self.end_node = end_node
        self.flow_dir = flow_dir
        self.edge_type=edge_type

class Network:
    def __init__(self):
        self.nodes = {}
        self.edges = {}
        self.element_type_counts = {}  # Track element counts
        self.load_nodes_from_csv()
        self.load_edges_from_csv()

    def load_nodes_from_csv(self):
        with open('uploaded_files/csvs_nodes.csv', mode='r') as file:
            reader = csv.reader(file)
            next(reader)  # Skip header row
            for row in reader:
                if len(row) < 7:
                    continue  # Skip rows that do not have enough columns
                node_id, element_type, x, y, _, _, item_tag, *_ = row
                x = float(x) if x else 0.0
                y = float(y) if y else 0.0
                tag_prefix = self.get_tag_prefix(element_type)
                tag_sequence_no = self.get_tag_sequence_no(tag_prefix)
                tag_suffix= determine_tag_suffix(item_tag)
                tag_measuredVariable = get_measured_variable_code(item_tag)
                tag_InstrumentTypeModifier = get_instrument_type_modifier(item_tag)
                drawing_id = row[4]  # Assuming drawing_id is the 5th column in CSV
                node = Node(node_id, element_type, item_tag, x, y, drawing_id, tag_prefix, tag_sequence_no,tag_suffix,tag_measuredVariable,tag_InstrumentTypeModifier)
                self.nodes[node_id] = node

    def load_edges_from_csv(self):
        with open('uploaded_files/csvs_edges.csv', mode='r') as file:
            reader = csv.reader(file)
            next(reader)  # Skip header row
            for row in reader:
                edge_id, run_id, edge_type, start_node, end_node, flow_dir, *_ = row
                edge_type=get_edge_type_between_nodes(start_node, end_node)
                edge = Edge(edge_id,run_id, start_node, end_node, edge_type,flow_dir)
                self.edges[edge_id] = edge

    def generate_item_tag(self, element_type):
        words = element_type.split()
        short_type = ''.join([word[:3] for word in words]).upper()
        # Generate a random number between 1 and 15
        random_number = random.randint(1, 15)

        if short_type not in self.element_type_counts:
            self.element_type_counts[short_type] = 0
        self.element_type_counts[short_type] += 1

        return f"{short_type}-{random_number}-{self.element_type_counts[short_type]}"

    def get_tag_prefix(self, element_type):
        # Derive a tag prefix from the element type, e.g., "Pump" becomes "PUM"
        return ''.join([word[:3].upper() for word in element_type.split()])

    def get_tag_sequence_no(self, tag_prefix):
        # Generate a sequence number for this tag prefix
        if tag_prefix not in self.element_type_counts:
            self.element_type_counts[tag_prefix] = 0
        self.element_type_counts[tag_prefix] += 1
        return self.element_type_counts[tag_prefix]


    def add_node(self, element_type, item_tag, nodes_csv, edges_csv, starting_item_tag):
        node_id = f"GENAINODE-{uuid.uuid4()}"
        item_tag = item_tag if item_tag else self.generate_item_tag(element_type)

        existing_element = find_existing_element(starting_item_tag,nodes_csv)

        x, y = calculate_new_coordinates_sub(existing_element, nodes_csv, new_nodes_sub)
        drawing_id = existing_element['drawing_id']
        
        tag_prefix = self.get_tag_prefix(element_type)
        tag_sequence_no = self.get_tag_sequence_no(tag_prefix)
        tag_suffix= determine_tag_suffix(item_tag)
        tag_InstrumentTypeModifier = get_instrument_type_modifier(item_tag)
        tag_measuredVariable = get_measured_variable_code(item_tag)
        node = Node(node_id, element_type, item_tag, x, y, drawing_id, tag_prefix, tag_sequence_no,tag_suffix,tag_measuredVariable,tag_InstrumentTypeModifier)
        self.nodes[node_id] = node
        self.append_node_to_csv(node)
        return node

    def add_edge(self, start_node_id, end_node_id, flow_dir='StartNode to EndNode'):
        edge_id = f"GENAIEDGE-{uuid.uuid4()}"
        run_id = str(uuid.uuid4()).replace('-', '').upper()
        edge_type=get_edge_type_between_nodes(start_node_id, end_node_id)
        edge = Edge(edge_id,run_id, start_node_id, end_node_id,edge_type, flow_dir)
        self.edges[edge_id] = edge
        self.append_edge_to_csv(edge)
        return edge    

    def append_node_to_csv(self, node):
        with open('uploaded_files/csvs_nodes.csv', mode='a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow([node.id, node.element_type, node.x, node.y, node.drawing_id, '', 
                             node.item_tag, node.tag_prefix, node.tag_sequence_no, node.tag_suffix, node.tag_measuredVariable,node.tag_InstrumentTypeModifier,'','',''])

    def append_edge_to_csv(self, edge):
        with open('uploaded_files/csvs_edges.csv', mode='a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow([edge.id, edge.run_id, edge.edge_type, edge.start_node, edge.end_node, edge.flow_dir, '', ''])

    def add_subnetwork(self, nodes_csv, edges_csv, user_input, starting_item_tag=None):
        subnetwork_structure = self.get_subnetwork_structure(user_input)

        starting_node = None
        if starting_item_tag:
            starting_node = self.find_node_by_item_tag(starting_item_tag)
        if starting_node is None:
            return {'status': 'error', 'message': f'The element with item tag {starting_item_tag} does not exist'}

        previous_node = starting_node
        new_item_tags = []
        for element in subnetwork_structure:
            if 'type' in element:
                new_node = self.add_node(element['type'], None, nodes_csv, edges_csv, starting_item_tag)
            elif 'tag' in element:
                new_item_tag = element['tag']
                element_type = determine_element_type(new_item_tag)
                print(f"Adding node with tag {new_item_tag} and type {element_type}")  # Debug output
                new_node = self.add_node(element_type, new_item_tag, nodes_csv, edges_csv, starting_item_tag)
            new_item_tags.append(new_node.item_tag)
            if previous_node:
                self.add_edge(previous_node.id, new_node.id)
            previous_node = new_node

        return {'status': 'success', 'message': f'Added subnetwork with item tags: {", ".join(new_item_tags)}'}


    def find_node_by_item_tag(self, item_tag):
        for node in self.nodes.values():
            if node.item_tag == item_tag:
                return node
        print(f"No node found with item tag: {item_tag}")
        return None

    def get_subnetwork_structure(self, user_input):
        templates = {
            # Add network templates as before
            "Process Fluid Network": [{'type': 'Pump'}, {'type': 'Pipe'}, {'type': 'Valve'}, 
                                       {'type': 'Reactor'}, {'type': 'Tank'}, {'type': 'Heat Exchanger'}],
            "Cooling Water Network": [{'type': 'Cooling Tower'}, {'type': 'Pump'}, 
                                      {'type': 'Heat Exchanger'}, {'type': 'Pipe'}, 
                                      {'type': 'Temperature Control System'}],
            "Steam Distribution Network": [{'type': 'Boiler'}, {'type': 'Steam Header'}, 
                                           {'type': 'Steam Trap'}, {'type': 'Pressure Relief Valve'}, 
                                           {'type': 'Condensate Return Line'}],
            "Compressed Air Network": [{'type': 'Air Compressor'}, {'type': 'Air Receiver'}, 
                                       {'type': 'Dryer'}, {'type': 'Filter'}, {'type': 'Piping'}, 
                                       {'type': 'Control Valve'}],
            "Fuel Gas Network": [{'type': 'Gas Pipeline'}, {'type': 'Flow Meter'}, 
                                 {'type': 'Pressure Regulator'}, {'type': 'Safety Shut-off Valve'}, 
                                 {'type': 'Burner'}],
            "Hydraulic Network": [{'type': 'Hydraulic Pump'}, {'type': 'Actuator'}, 
                                  {'type': 'Valve'}, {'type': 'Reservoir'}, {'type': 'Piping'}],
            "Vacuum System Network": [{'type': 'Vacuum Pump'}, {'type': 'Vacuum Header'}, 
                                      {'type': 'Ejector'}, {'type': 'Condenser'}, 
                                      {'type': 'Control Valve'}],
            "Chemical Injection Network": [{'type': 'Dosing Pump'}, {'type': 'Chemical Storage Tank'}, 
                                           {'type': 'Injection Valve'}, {'type': 'Flow Meter'}],
            "Fire Water Network": [{'type': 'Fire Water Pump'}, {'type': 'Fire Hose'}, 
                                  {'type': 'Hydrant'}, {'type': 'Sprinkler'}, 
                                  {'type': 'Deluge System'}],
            "Wastewater Network": [{'type': 'Sump'}, {'type': 'Pump'}, {'type': 'Pipe'}, 
                                   {'type': 'Valve'}, {'type': 'Clarifier'}, 
                                   {'type': 'Filter'}, {'type': 'Neutralizer'}],
            "Instrumentation and Control Network": [{'type': 'Pressure Sensor'}, 
                                                     {'type': 'Temperature Sensor'}, 
                                                     {'type': 'Flow Sensor'}, 
                                                     {'type': 'PLC'}, {'type': 'SCADA System'}, 
                                                     {'type': 'Control Valve'}],
            "Electrical Power Distribution Network": [{'type': 'Transformer'}, 
                                                       {'type': 'Switchgear'}, 
                                                       {'type': 'Circuit Breaker'}, 
                                                       {'type': 'Electrical Panel'}, 
                                                       {'type': 'Cable'}, {'type': 'Busbar'}],
            "Gas Distribution Network": [{'type': 'Gas Storage Vessel'}, 
                                          {'type': 'Pressure Regulator'}, 
                                          {'type': 'Flow Meter'}, {'type': 'Pipeline'}, 
                                          {'type': 'Valve'}],
        }

        # Check if user_input matches a template
        if user_input in templates:
            return templates[user_input]
        
        # Custom input
        return self.parse_custom_input(user_input)

    def parse_custom_input(self, user_input):
        parts = user_input.split('existing_item_tag=')
        elements_part = parts[0].replace('Network elements:', '').strip()
        components = elements_part.split(',')
        print("Components parsed from input:", components)
        # Check if any network element (excluding existing_item_tag) contains a number
        if any(char.isdigit() for comp in components for char in comp):
            result = [{'tag': comp.strip()} for comp in components if comp.strip()]
            print("Parsed as tags:", result)  # Debugging output
            return result
        else:
            result = [{'type': comp.strip()} for comp in components if comp.strip()]
            print("Parsed as types:", result)  # Debugging output
            return result


def get_item_tags_from_csv(nodes_csv):
    """
    Reads item tags from the given CSV file and returns a list of non-empty item tags.
    
    Parameters:
        nodes_csv (str): Path to the CSV file containing item tags.

    Returns:
        list: A list of non-empty item tags.
    """
    item_tags = []

    # Open the CSV file
    with open(nodes_csv, mode='r', newline='', encoding='utf-8') as file:
        reader = csv.DictReader(file)  # Read the file as a dictionary
        
        # Iterate through each row and extract the item_tag
        for row in reader:
            # Assuming the item tag is in the column named "ItemTag"
            tag = row.get('ItemTag')  # Use .get to avoid KeyError
            if tag and tag.strip():  # Check if tag is not None or empty
                item_tags.append(tag.strip())  # Add the cleaned tag to the list

    return {'status': 'success', 'message': f'The following ItemTags are present in csv {item_tags}'}


# Updated system prompt to handle both additions and removals
system_prompt = """
You are an AI that manages CSV files containing nodes and edges. You will handle user requests for adding, updating, or deleting nodes and edges.
Special Notes:
- Pay close attention to conjunctions like "and" or separators like commas ",", fullstops "." . Use them to identify multiple elements in the user's request.
- Ensure that each extracted item tag is valid and distinct from others. Avoid treating multiple tags as a single entity.
- If user gives both type and item tag in prompt only consider the item tag and return that. 
- If user asks to add something to a vessel via a nozzle or though user won't explicitly mention anything about adding nozzle while adding element to a vessel, you need to add a nozzle as a first element of subnetwork and then remaining elements as subnetwork.

For adding a subnetwork:
- User will ask to add a subnetwork to existing network and may or maynot provide the elements of subnetwork, understand the prompt of subnetwork properly
- If user asks to add something to a vessel via a nozzle or though user won't explicitly mention anything about adding nozzle while adding element to a vessel, you need to add a nozzle as a first element of subnetwork and then remaining elements as subnetwork.
- In case of adding subnetwork into the existing subnetwork user may give us two types of prompts, user may ask us with specific elements that are there in subnetwork, else just give us the template name of the subnetwork. When given elements don't consider pipe as an element, don't return it back if user gives pipe in user_prompt.
- If there are any spelling mistakes in type of element given by user then you understand them and correct it, mostly the element types are valve, nozzle, cooler, pump, vessel, sensor, heat exchanger, etc, you correct them from your knowledge.  
- If user asks us to add specific elements your response should contain the elements with comma separated values and user will ask to connect this subnetwork to an existing element, you also need to give that. If the prompt also contains to add a pipe, dont consider that as a node, don't return that to network elements
- If  user gives both item tags and types of elements in prompt, just give the item tags, if only types are given, give type, if only item tags are given give item itags.Don't include pipe into this Network elements
- User may also ask some complex prompts for subnetwork without mentioning thm as subnetwork, the elements might be connected to each other, in such cases understand the pompts carefully and treat as subnetwork only if connection between elements is requested somehow by user. 
Example: 1) ADD NOZZLE TO VES-5003 and attach a pipe to the nozzle followed by a valve
2) Add nozzle and attach a pipe and valve to VES-5003
3) Insert a vessel with pressure gauge next to VES-5003  
These are some examples for complex prompts related to subnetwork.
"Operation: sub_network: Network elements: <elements of subnetwork with comma separated>, existing_item_tag=<item_tag>" strictly follow the structure given including symbols like (: , =), dont include pipe if it is there.
-If prompt only contains the sub network template and existing item tag your response should only contain the name of the template "Operation: template: <name of template>, existing_item_tag=<existing_item_tag>".
-Clearly understand the difference between subnetwork and multiple opearations. User clearly mentions subnetwork in prompt, understand that. Don't think subnetwork as multiple elements.

For adding a new element between two existing items:
- Understand the user prompt if user asks to add a new element between existing elements and collect the item tags of all three elements, new element, existing element-1 and existing element-2.
- Consider all synonyms of add.
In case of adding only one element between two an existing elements, Your response should only contain the operation and extracted tags in the format:
 Operation: B/W 2 elements, NewItemTag: <new_item_tag>, ExistingItemTag1: <existing_item_tag1>, ExistingItemTag2: <existing_item_tag2>,

User may also give multiple operations in the single prompt like adding more than one elements to the same element, or adding different new elements to different existing elements, updating multiple elements or perform multiple various opeartions adding then updating or then deleting in any order:
For multiple operations:
- If user asks to add something to a vessel via a nozzle or though user won't explicitly mention anything about adding nozzle while adding element to a vessel, you need to add a nozzle as a first element of subnetwork and then remaining elements as subnetwork.
- If the user prompt also contains size do not treat it as single, treat as multiple prompts.
- Understand the prompt, if user asks many operations in a single prompt it can be multiple additions, deletions, updations or a combination of all operations, consider the following
- Consider all synonyms of add, update, delete.
- User can also simply give normal prompt like add element1, element 2, elment 3 and element 4 to so and so element, or add element and element 2 to so and so element or any other form that contains more than one addition or updation or deletion or more than one operaton. Understand the user well.
- Your response should return a dictionary with two keys: "
    "   'addition_dict' - where the key is the existing node's item tag and the value is a list of new node names. "
    "   'updates_dict' - where the key is the existing node's item tag and the value is the updated values."
- If there are multiple new nodes or updates, return them all in the appropriate dictionary."
- Ensure the item tags and node names are extracted and properly formatted.
In case of the prompt contains multiple operations or multiple additions to same or different existing elements or deltetions in the prompt,
If in case user asks to add or mention anything about size of nominal diameter of a particular element give the new element's item tag as key and new size as value in update_dict as an integer. Do not give anything like operation:size here.
If user asks to change only the type of an element, in the updation_dict you need to give like this: operation:type as first element and the next is you need to give the item tag of old element as key and new type as value.
 your response should only contain the dictionary as mentioned in the form 
"{
'addition_dict': {
},
'updation_dict' : { 
},
'deletions_dict':{
"Deletion":<Deletion_itemtag>
},
}"


For adding a single new element to an existing item:
- If user asks to add something to a vessel via a nozzle or though user won't explicitly mention anything about adding nozzle while adding element to a vessel, you need to add a nozzle as a first element of subnetwork and then remaining elements as subnetwork.
- Consider all synonyms of add.
- Read whole prompt carefully.
- If contains more than one addition treat as multiple prompts.
- If the user prompt also contains size do not treat it as single, treat as multiple prompts.
- User prompt will only contain one single element element to be added to an existing element.
- Don't treat multiple elements as single element.
- If there are commas between elements to be added and some plural words present in prompt do not treat it as single element, treat them as multiple elements. 
In case of adding only one element to an existing element, Your response should only contain the operation and extracted tags in the format: 
Operation: adding, NewItemTag: <new_item_tag>, ExistingItemTag: <existing_item_tag>

For removing an element:
- Consider all synonyms of remove.
- Identify the item tag of the element to be removed.
- Remove the corresponding node and its associated edges from the CSV files.
- If prompt also contains anything about remove connected line, pipe, don't consider that, just give element. Don't bother much about it.
In case of removal Your response should only contain the operation and extracted tag in the format:
 Operation: deleting, RemoveItemTag: <remove_item_tag>

For updating or replacing an element:
- Consider all synonyms of update
- User may ask to replace an element with other element
- Gather the item tag of existing element, and new element
- Give response of existing item tag and the new item tag of element
In case of updating or replacing an element your response should only contain the dictionary, it should only contain like this: key is the item tag and value is only new item tag
If in case user asks to change or update or increase or decreasethe size of nominal diameter of a particular element give the element's item tag as key and new size as value in dictionary as an integer.
If user asks to change only the type of an element, you need to give like this: operation:type as first element and the next element is you need to give the item tag of old element as key and new type as value.
"{
item_type_updates_dict = {  

}
}"

For updating the position of an element:
- Consider relocate, swap as this operation
- User will ask to just relocate or swap two existing elements
- If the user requests to exchange the positions of two existing elements then you need to gather their item tags.
In case of updating positions, relocating or swaping elements you response should only contain the two item tags like: "Relocate_elements: <Item_Tag1>, <Item_Tag2>"

- If user asks to give the item tags or what nodes are present you need to give a response like <Request for ItemTags>

You should understand and interpret prompts in various formats, whether
 the user wants to add or remove or update elements, and handle the tasks appropriately.
"""

response_system_prompt="""You are an AI model designed to assist users with operations related to a PID (Piping and Instrumentation Diagram). In a PID diagram:
                                Nodes represent elements (such as components, valves, pipes).
                                Edges represent the connections between those elements.
                                Users will provide requests for tasks such as:

                                Adding single or multiple elements.
                                Performing operations like adding elements, adding a subnetwork, removing or replacing elements, updating sizes of elements etc.
                                The requests may include various synonyms or phrasing in different orders.
                                Your role is to:
                                If there are any spelling mistakes in type of element given by user then you understand them and correct it, mostly the element types are valve, nozzle, cooler, pump, vessel, sensor, heat exchanger, etc, you correct them from your knowledge.
                                You dont need to tell back user about spelling mistakes, just understand them by your own. 
                                Identify the user's intent and clearly summarize the actions they've requested straight forwrd, without any extra info.
                                Confirm the actions by asking if the user's request matches your understanding. 
                                If the prompt is lengthy, break it into simple, clear steps, and ask the user if that's correct.
                                Avoid overwhelming the user. Keep the explanation concise and clear—use points or steps, not multiple iterations of the same information.
                                If the user's prompt includes item tags like NewItemTag:<...>, ExistingItemTag:<...>, or similar, respond accordingly.
                                If the user's input is unrelated to PID or contains gibberish (e.g., names,pronouns,places of cities or random words not related to PID), If the prompt also misses exising item tag when adding of new elememts is requested then also gven an error'Error:' Provide existing item tag to which it needs to be added
                                In this case start your response with 'Error:'"politely ask them to provide a relevant prompt related to the PID diagram. Don't give much explanaton just be to point """


def get_user_data_give_response(user_prompt, api_key_type):
    assistant_reply = ""

    try:
        if api_key_type == "gemini":
            genai.configure(api_key=os.getenv("API_KEY"))
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(f"{response_system_prompt}\nUser: {user_prompt}")
            assistant_reply = response.text.strip()

        elif api_key_type == "azure_openai":
            from openai import AzureOpenAI
            azure_oai_endpoint = os.getenv("AZURE_OAI_ENDPOINT")
            azure_oai_key = os.getenv("AZURE_OAI_KEY")
            azure_oai_deployment = os.getenv("AZURE_OAI_DEPLOYMENT")
        
            client = AzureOpenAI(
                azure_endpoint=azure_oai_endpoint,
                api_key=azure_oai_key,
                api_version="2024-08-01-preview"
            )
        
            messages_array = [
                {"role": "system", "content": response_system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            response = client.chat.completions.create(
                model=azure_oai_deployment,
                temperature=0.7,
                max_tokens=1200,
                messages=messages_array
            )
            assistant_reply = response.choices[0].message.content

        elif api_key_type == "openai":
            import openai
            openai.api_key = os.getenv("api")
            input_prompt = [
                {"role": "system", "content": response_system_prompt},
                {"role": "user", "content": user_prompt}
            ]

            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=input_prompt,
            )

            assistant_reply = response.choices[0].message['content'].strip()

        print("Model response:", assistant_reply)
        
        # Ensure the response is in a valid JSON format
        if "Error" in assistant_reply:
            return {
                'result': 'error',
                'message': f'Model response: {json.dumps({"error": assistant_reply}, indent=2)}'
            }
        else:
            return {
                'result': 'success',
                'message': json.dumps({"response": assistant_reply}, indent=2)
            }
    except Exception as e:
        return {
            'result': 'error',
            'message': f"Exception occurred: {str(e)}"
        }
 

def get_user_data_and_update_csv( user_prompt, nodes_csv, edges_csv,api_key_type):
    # Modularize client setup based on selected key type
    if api_key_type == "gemini":
        genai.configure(api_key=os.getenv("API_KEY"))
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(f"{system_prompt}\nUser: {user_prompt}")
        assistant_reply = response.text.strip()

    elif api_key_type == "azure_openai":
        from openai import AzureOpenAI
        azure_oai_endpoint = os.getenv("AZURE_OAI_ENDPOINT")
        azure_oai_key = os.getenv("AZURE_OAI_KEY")
        azure_oai_deployment = os.getenv("AZURE_OAI_DEPLOYMENT")
    
        print(azure_oai_endpoint)
        # Initialize the Azure OpenAI client...
        client = AzureOpenAI(
        azure_endpoint = azure_oai_endpoint,
        api_key=azure_oai_key,  
        api_version="2024-08-01-preview"
        )
    
        messages_array =  [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
        ]
            
        response = client.chat.completions.create(
                    model=azure_oai_deployment,
                    temperature=0.3,
                    max_tokens=2500,
                    messages=messages_array
                )
    
        assistant_reply = response.choices[0].message.content

    elif api_key_type == "openai":
        openai.api_key = os.getenv("api")
        # Using the new API interface
        input_prompt = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        # Generate content based on the combined input
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=input_prompt,
                #max_tokens=300
            )

            # Attempt to access the response text
            assistant_reply = response.choices[0].message['content'].strip()
        except Exception as e:
            print(f"An error occurred: {e}")

    print("Model response:", assistant_reply)

    # Check if the response indicates an addition or removal
    if "Operation: adding" in assistant_reply:
        # Extract item tags for addition
        match = re.match(r"Operation:\s*adding,\s*NewItemTag:\s*(\S+),\s*ExistingItemTag:\s*(\S+)", assistant_reply)
        if match:
            new_item_tag = match.group(1)
            existing_item_tag = match.group(2)
            result = add_new_node(new_item_tag, nodes_csv,edges_csv, existing_item_tag)
            add_edges(new_item_tag, existing_item_tag, nodes_csv, edges_csv)
            if result['status'] == 'error':
                return result
            else:
                return {'status':'success','message':f"Added element:{new_item_tag}"}
        else:
            return{'status':'error','message':'Could not extract item tags from model response'}

    elif "Operation: B/W 2 elements" in assistant_reply:
         match = re.match(r"Operation:\s*B/W\s*2\s*elements,\s*NewItemTag:\s*(\S+),\s*ExistingItemTag1:\s*(\S+),\s*ExistingItemTag2:\s*(\S+)", assistant_reply.strip())
         if match:
            new_item_tag = match.group(1)
            node1_item_tag = match.group(2)
            node2_item_tag = match.group(3)
            #print(f"Adding new element between {node1_item_tag} and {node2_item_tag} with tag {new_item_tag}")
                # Add the new node and edges
            result=add_bw_node(new_item_tag, nodes_csv, node1_item_tag, node2_item_tag,edges_csv)
            add_edges(new_item_tag, node1_item_tag, nodes_csv, edges_csv)
            add_edges(new_item_tag, node2_item_tag, nodes_csv, edges_csv)
            if result['status'] == 'error':
                return result
            else:
                return {'status':'success','message': f"Added {new_item_tag} b/w {node1_item_tag} and {node2_item_tag}"}
         else:
            return{'status':'error','message':'Could not extract item tags from model response'}
    
    elif "template" in assistant_reply:
        # Initialize extracted values
        extracted_template = None
        extracted_item_tag = None

        # Check if the assistant reply contains both 'template' and 'item tag' information
        template_match = re.search(r'template:\s*([A-Za-z\s]+),\s*existing_item_tag=([\w\W]+)', assistant_reply)

        if template_match:
            extracted_template = template_match.group(1).strip()
            extracted_item_tag = template_match.group(2).strip()
            
            #print(f"Template: {extracted_template}")
            #print(f"Item Tag: {extracted_item_tag}")
            
            network = Network()
            result = network.add_subnetwork(nodes_csv, edges_csv, extracted_template, extracted_item_tag)
            if result['status'] == 'error':
                return result
            else:
                # Extract item tags from the result and include them in the success message
                added_item_tags = result.get('message', '').split(':')[-1].strip()  # Extract the item tags from the message
                return {
                    'status': 'success',
                    'message': f'Successfully added template {extracted_template} with item tags: {added_item_tags}'
                }
            
    elif "sub_network" in assistant_reply:
        # Updated parsing logic for assistant reply
        extracted_elements = None
        starting_item_tag = None

        # Adjusted regular expression to handle spaces after commas and complex tags
        network_match = re.search(r'Network elements:\s*([\w\s,-]+)\s*existing_item_tag=([\w-]+)', assistant_reply)

        if network_match:
            extracted_elements = network_match.group(1).strip().rstrip(',')  # Extract the elements string directly
            starting_item_tag = network_match.group(2).strip()  # Extract the starting item tag
            print("Extracted elements:", extracted_elements)  # Debugging output
            print("Starting item tag:", starting_item_tag)  # Debugging output

        
        if network_match:
            extracted_elements = network_match.group(1).strip().rstrip(',')  # Extract the string of elements directly
            starting_item_tag = network_match.group(2).strip()
            print(extracted_elements)
            print(starting_item_tag)
            network = Network()
            result=network.add_subnetwork(nodes_csv,edges_csv, extracted_elements, starting_item_tag)
            if result['status'] == 'error':
                return result
            else:
                # Extract item tags from the result and include them in the success message
                added_item_tags = result.get('message', '').split(':')[-1].strip()  # Extract the item tags from the message
                return {
                    'status': 'success',
                    'message': f'Successfully added subnetwork with {added_item_tags}'
                }

    elif "Operation: deleting" in assistant_reply:
        # Extract item tag for removal
        match = re.match(r"Operation:\s*(\S+),\s*RemoveItemTag:\s*(\S+)", assistant_reply)
        if match:
            remove_item_tag = match.group(2)
            #print(f"Removing element with tag {remove_item_tag}")
            result=remove_node_and_update_edges(remove_item_tag, nodes_csv, edges_csv)
            if result['status'] == 'error':
                return result
            else:
                return {'status':'success','message':f"Deleted {remove_item_tag} successfully"}
            #if remove_node_and_update_edges:
                #print("Element deleted successfully!")


        else:
            return{'status':'error','message':'Could not extract item tags from model response'}
    

    elif "addition_dict" in assistant_reply:
        # Function to extract dictionaries from response
        def extract_dictionaries(assistant_reply):
            dict_match = re.search(r'\{.*\}', assistant_reply, re.DOTALL)
            if dict_match:
                dict_str = dict_match.group(0)
                return ast.literal_eval(dict_str)
            return {}
        
        generated_dict = extract_dictionaries(assistant_reply)

        success_occurred = False  # Flag to track if any operation succeeded
        
        # Process additions
        if 'addition_dict' in generated_dict and generated_dict['addition_dict']:
            result = add_nodes_from_dict(generated_dict['addition_dict'], 'uploaded_files/csvs_nodes.csv', 'uploaded_files/csvs_edges.csv')
            if result['status'] == 'success':
                success_occurred = True
                edges_changed = add_edges_from_dict(generated_dict['addition_dict'], 'uploaded_files/csvs_nodes.csv', 'uploaded_files/csvs_edges.csv')
                if edges_changed:
                    print("Nodes and edges were updated successfully!")
                else:
                    print("Nodes were updated but no changes were made to edges.")
            else:
                return result

        # Process updates
        if 'updation_dict' in generated_dict and generated_dict['updation_dict']:
            result = update_item_types(nodes_csv, generated_dict['updation_dict'])
            if result['status'] == 'error':
                return result
            else:
                success_occurred = True  # Update succeeded
                print("Updated the element type.")

        # Process deletions
        if 'deletions_dict' in generated_dict and generated_dict['deletions_dict']:
            del_dict = generated_dict['deletions_dict']
            remove_item_tag = del_dict.get("Deletion")
            result = remove_node_and_update_edges(remove_item_tag, nodes_csv, edges_csv)
            if result['status'] == 'error':
                return result
            else:
                success_occurred = True  # Deletion succeeded
                print("Element deleted successfully!")

        # Return a combined success message if any operation was successful
        if success_occurred:
            added_nodes_list = [node for sublist in generated_dict['addition_dict'].values() for node in sublist]
            return {'status': 'success', 'message': f'Performed operations successfully. The elements added are: {added_nodes_list}'}
        else:
            return {'status': 'error', 'message': 'No operations were performed.'}

    elif 'Relocate_elements' in assistant_reply:
        # Regular expression to extract item tags
        regex = r"Relocate_elements:\s*(.+?),\s*(.+)"
        # Apply regex
        match = re.match(regex, assistant_reply)

        if match:
            element_1 = match.group(1)  # Item tag before the comma
            element_2 = match.group(2)   # Item tag after the comma
            print(f"Before Comma: {element_1}")
            print(f"After Comma: {element_2}")
        else:
            print("No match found.")
        result= swap_node_info(element_1, element_2 , nodes_csv)
        #if coordinates_changed:
            #print("Nodes coordinates updated successfully!")
        if result['status'] == 'error':
                return result
        else:
            return {'status':'success','message':'Updated'}
    
    elif 'item_type_updates_dict' in assistant_reply:
            def extract_dictionary(assistant_reply):
                dict_match = re.search(r'\{.*\}', assistant_reply, re.DOTALL)
                if dict_match:
                    dict_str = dict_match.group(0)
                    return ast.literal_eval(dict_str)
                return {}
            item_type_updates = extract_dictionary(assistant_reply)
            #print(item_type_updates)
            result = update_item_types(nodes_csv, item_type_updates['item_type_updates_dict'])
            print(item_type_updates)
            #if update_type:
                #print("Updated the element type")
            if result['status'] == 'error':
                return result
            else:
                return {'status':'success','message':'Updated'}
            
    elif 'Request for ItemTags' in assistant_reply:
        result= get_item_tags_from_csv(nodes_csv)
        if result['status'] == 'success':
                return result
    
    else:
        return{'status':'error','message':'No valid response'}

# Example usage
if __name__ == "__main__":
    # Example user prompt
    #user_prompt = "Add N-126 and P-164 to VES-5003"
    #user_prompt = "Insert a new nozzle labeled as N-6 onto the element with the item tag VES-301."
    #user_prompt = "Remove an element with item tag V-1235."
    #user_prompt = "Remove an element with item tag N7"
    #user_prompt = "Remove an element with item tag pum-1"
    #user_prompt = "Attach N-1245 onto the element VES-5064"
    #user_prompt= "add vent nozzle as N-7 between elements with item tags MP-5004 and VES-301"
    #user_prompt = "add vent nozzle as V-432 between nodes with item tags VES-301 and VES-5003"
    #user_prompt = "add vent nozzle as N120 to node with item tag VES-5003, and add a new pump as P100 to node with item tag MP-5004, Delete N-7"
    #user_prompt= "Replace the element N-194 with Valve V-6"
    #user_prompt="Add a subnetwork, attached to VES-5003 and has the following components, cooler, pump, valve, pipe"
    #user_prompt="Add a subnetwork  Compressed Air Network and attach it to VES-5003"
    #user_prompt="add vent nozzle as N120 to VES-5064, and add a new pump as P100 to N7, update type of N7 to Valve"
    #LY-5560A
    #user_prompt="Add sub network with nozzle N-1, pipe P-1 and valve V-2 to VES-5003"
    #user_prompt="Add sub network with  N-1, P-1 and V-2 to VES-5003"
    #user_prompt="Add N-123,V-6 to VES-5064"
    user_prompt="Chnage size of VES-5003 TO 300"

    # CSV file to be updated
    nodes_csv = 'uploaded_files/csvs_nodes.csv'
    edges_csv = 'uploaded_files/csvs_edges.csv'

    #initial_row_count = update_csv('uploaded_files/csvs_nodes.csv')

    # Call the function to process the user input and update the CSV file
    get_user_data_and_update_csv(user_prompt, nodes_csv, edges_csv)
