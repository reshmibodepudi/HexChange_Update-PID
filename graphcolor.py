import matplotlib
matplotlib.use('Agg')  # Use the non-interactive 'Agg' backend

from flask import session
import pandas as pd
import glob
import os
import networkx as nx
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.image import imread
import pandas as pd

def get_graph(path, graph_output_path):
    # Check if the path is correct
    if not os.path.exists(path):
        print(f"Path does not exist: {path}")
        return
    
    # Load PID image if it exists in 'uploaded_files' folder
    image_files = glob.glob(os.path.join(path, "*.[Pp][Nn][Gg]")) + \
                  glob.glob(os.path.join(path, "*.[Jj][Pp][Gg]")) + \
                  glob.glob(os.path.join(path, "*.[Jj][Pp][Ee][Gg]"))
    
    if not image_files:
        print("No PID image found in the directory.")
        return
    
    pid_image_path = image_files[0]  # Assuming there is only one image in 'uploaded_files'
    
    # Load the image to use for alignment and get its dimensions
    img = imread(pid_image_path)
    img_height, img_width = img.shape[:2]
    
    # Get all edges CSV files
    all_edge_files = glob.glob(os.path.join(path, "*edges.csv"))
    if not all_edge_files:
        print(f"No edge CSV files found in the directory: {path}")
        return

    edge_list = []

    for filename in all_edge_files:
        df = pd.read_csv(filename, decimal=',')
        df.columns = df.columns.str.strip()  # Remove any leading/trailing whitespace

        # Automatically identify and rename the first column to "EDGEID"
        first_column = df.columns[0]
        df = df.rename(columns={first_column: "EDGEID", 
                                "RunID": "RUNID", 
                                "Type": "EDGETYPE", 
                                "StartNode": "STARTNODE",
                                "EndNode": "ENDNODE", 
                                "FlowDir": "FLOWDIR", 
                                "DrawingID": "DRAWINGID", 
                                "ItemTag": "ITEMTAG"})
        
        edge_list.append(df)

    edges = pd.concat(edge_list, axis=0, ignore_index=True)

    edges['ITEMTAG'] = edges['ITEMTAG'].astype(str)

    # Get all nodes CSV files
    all_node_files = glob.glob(os.path.join(path, "*nodes.csv"))
    if not all_node_files:
        print(f"No node CSV files found in the directory: {path}")
        return

    node_list = []
    for filename in all_node_files:
        df = pd.read_csv(filename, decimal=',')
        node_list.append(df)

    nodes = pd.concat(node_list, axis=0, ignore_index=True)

    # Rename column names to match expected names
    nodes = nodes.rename(columns={ 
        "ID": "NODEID", "Type": "NODETYPE", "XCoordinate": "XCOORDINATE", "YCoordinate": "YCOORDINATE",
        "DrawingID": "DRAWINGID", "Subtype": "NODESUBTYPE", "ItemTag": "ITEMTAG", "NominalDiameter":"NOMINALDIAMETER"
    })
    nodes['ITEMTAG'] = nodes['ITEMTAG'].astype(str)

    # Fill missing node subtype values
    nodes['NODESUBTYPE_filled'] = nodes[['NODETYPE', 'NODESUBTYPE']].apply(
        lambda x: x['NODETYPE'] if pd.isna(x['NODESUBTYPE']) else x['NODESUBTYPE'], axis=1)

    # Ensure coordinates are numeric and drop nodes with missing coordinates
    nodes = nodes[nodes['XCOORDINATE'] != 'XCOORDINATE']  # Filter out invalid rows
    nodes['XCOORDINATE'] = pd.to_numeric(nodes['XCOORDINATE'])
    nodes['YCOORDINATE'] = pd.to_numeric(nodes['YCOORDINATE'])

    # Drop strange or invalid edges
    edges = edges[edges['EDGEID'] != 'ID']
    edges = edges.dropna(subset=['STARTNODE', 'ENDNODE'])

    # Swap STARTNODE and ENDNODE based on FLOWDIR
    edges['STARTNODE'], edges['ENDNODE'] = zip(*edges.apply(
        lambda row: (row['ENDNODE'], row['STARTNODE']) if row['FLOWDIR'] == 'EndNode to StartNode' else (row['STARTNODE'], row['ENDNODE']),
        axis=1))

    # Create a directed graph from the edges dataframe
    G = nx.from_pandas_edgelist(edges, source='STARTNODE', target='ENDNODE', edge_attr=True, create_using=nx.DiGraph())

    # Add node attributes to the graph
    node_attrs = nodes.set_index('NODEID')[['NODETYPE', 'NODESUBTYPE_filled', 'ITEMTAG', 'XCOORDINATE', 'YCOORDINATE']].to_dict('index')
    nx.set_node_attributes(G, node_attrs)

    # Identify single nodes that are not connected to any edges
    all_node_ids = set(nodes['NODEID'])
    edge_node_ids = set(edges['STARTNODE']).union(set(edges['ENDNODE']))
    single_node_ids = all_node_ids - edge_node_ids

    # Add single nodes to the graph
    for node_id in single_node_ids:
        G.add_node(node_id, **node_attrs[node_id])

    # Define an offset value for downward adjustment
    y_offset = 50  # Adjust this value to control how far down the graph should move
    x_offset = 50

    # Get node positions for visualization, scaled to match image dimensions
    positions = {
        node: (
            attr['XCOORDINATE'] * img_width / nodes['XCOORDINATE'].max() - x_offset,
            (attr['YCOORDINATE'] * img_height / nodes['YCOORDINATE'].max()) - y_offset  # Apply downward offset
        )
        for node, attr in node_attrs.items()
    }

    # Ensure every node in the graph has a position
    missing_positions = [node for node in G.nodes() if node not in positions]
    if missing_positions:
        print(f"Warning: The following nodes are missing positions: {missing_positions}")
        # Remove nodes without positions from the graph
        G.remove_nodes_from(missing_positions)
    
    # Access initial_row_count from session
    initial_row_count = session.get('initial_row_count', 0)  # Default to 0 if not set
    print(initial_row_count)
    
    # Recalculate or modify initial_row_count during execution
    df = pd.read_csv('uploaded_files/csvs_nodes.csv')
    final_row_count = len(df)
    print(final_row_count)

    highlighted_nodes = nodes.iloc[initial_row_count:]
    highlighted_node_ids = highlighted_nodes['NODEID'].tolist()
    print(initial_row_count)
    # Highlight node colors
    # node_colors = []
    # for node in G.nodes():
    #     if node in highlighted_node_ids:
    #         node_colors.append('blue')  # Highlighted nodes (greater than initial_row_count)
    #     else:
    #         node_colors.append('orange')  # Existing nodes

    # Highlight the nodes that contain "GENAINODE" in their ID
    node_colors = ['blue' if "GENAINODE" in node else 'orange' for node in G.nodes()]

    # Set the figure size to match the image's dimensions
    fig = plt.figure(figsize=(img_width / 100, img_height / 100))  # Adjust for DPI scaling
    plt.imshow(img, extent=[0, img_width, 0, img_height], aspect='auto', alpha=0.3)  # Increase transparency

   # Overlay the graph on top of the image
    nx.draw(G, pos=positions, with_labels=False, node_size=40, node_color=node_colors,
            font_size=10, font_weight='bold', edge_color='gray', width=0.8,
            arrows=True, arrowsize=5)

    # Annotate nodes with "GENAI" in their ID with their type
    for node_id, attr in G.nodes(data=True):
        if "GENAI" in str(node_id):  # Check if "GENAI" is in the node ID
            node_type = attr.get('NODETYPE', 'Unknown')  # Retrieve NODETYPE, default to 'Unknown'
            x, y = positions[node_id]  # Get the position of the node
            plt.text(
                x + 6, y + 5,  # Slightly offset the text by 5 units in both x and y directions
                f"{node_type}", 
                fontsize=10, color='darkgreen',  # Change text color to dark green
                verticalalignment='bottom', horizontalalignment='right'  # Adjust alignment
            )


    # Save the graph as an image to the provided path with the same size as the PID image
    plt.savefig(graph_output_path, dpi=100, bbox_inches='tight', pad_inches=0)  # Use 'tight' to trim excess whitespace
    plt.close()  # Close the plot to avoid memory issues


