import os
import pandas as pd
from flask import Flask, request, redirect, url_for, render_template, flash, send_file, jsonify
from werkzeug.utils import secure_filename
import shutil
from dotenv import load_dotenv
from updated import get_user_data_and_update_csv,get_user_data_give_response
from graphcolor import get_graph
from flask import send_file
import zipfile, io
from flask import session


load_dotenv()

app = Flask(__name__)
app.secret_key = 'your_secret_key'
app.config['UPLOAD_FOLDER'] = 'uploaded_files'
app.config['ALLOWED_EXTENSIONS'] = {'csv', 'png','jpg','jpeg'}  # Include 'png' in allowed extensions
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Ensure the upload folder and graphs directory exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.join('static', 'graphs'), exist_ok=True)


def allowed_file(filename):
    # Check if the file has an allowed extension
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@app.route('/')
def upload_nodes_form():
    image_file = url_for('static', filename='image.jpg')  # Adjust the path to your image
    return render_template('index1.html', image_file=image_file)

@app.route('/upload_folder', methods=['POST'])
def upload_folder():
    if 'files' not in request.files:
        flash('No files part')
        return redirect(request.url)

    files = request.files.getlist('files')
    if not files:
        flash('No selected folder or files.')
        return redirect(request.url)

    folder_path = app.config['UPLOAD_FOLDER']
    os.makedirs(folder_path, exist_ok=True)

    # Clear previous files in the upload folder
    for existing_file in os.listdir(folder_path):
        file_path = os.path.join(folder_path, existing_file)
        if os.path.isfile(file_path):
            os.remove(file_path)

    nodes_file, edges_file, image_file = None, None, None

    for file in files:
        filename = secure_filename(file.filename)
        file_path = os.path.join(folder_path, filename)
        file.save(file_path)

        # Check if the file is a CSV and classify it based on its content
        if filename.endswith('.csv'):
            df = pd.read_csv(file_path)
            if all(column in df.columns for column in ['ID', 'Type', 'XCoordinate', 'YCoordinate']):  # Nodes file columns
                nodes_file = file_path
            elif all(column in df.columns for column in ['ID', 'RunID', 'Type', 'StartNode', 'EndNode']):  # Edges file columns
                edges_file = file_path
        elif filename.lower().endswith(('.png', '.jpg', '.jpeg')):
            image_file = filename

    if not nodes_file or not edges_file:
        flash('Both nodes and edges CSV files are required in the uploaded folder.')
        return redirect(url_for('upload_nodes_form'))

    # Rename the files to standardized names
    os.rename(nodes_file, os.path.join(folder_path, 'csvs_nodes.csv'))
    os.rename(edges_file, os.path.join(folder_path, 'csvs_edges.csv'))

    if not validate_nodes_csv(os.path.join(folder_path, 'csvs_nodes.csv')):
        flash('The nodes CSV file does not contain the required columns.')
        return redirect(url_for('upload_nodes_form'))

    if not validate_edges_csv(os.path.join(folder_path, 'csvs_edges.csv')):
        flash('The edges CSV file does not contain the required columns.')
        return redirect(url_for('upload_nodes_form'))

    flash('Folder uploaded successfully!')
    return redirect(url_for('prompt', folder=folder_path, image_file=image_file))


def validate_nodes_csv(filepath):
    required_columns = ['ID', 'Type', 'XCoordinate', 'YCoordinate', 'DrawingID', 'Subtype', 
                        'ItemTag', 'TagPrefix', 'TagSequenceNo', 'TagSuffix', 
                        'MeasuredVariableCode', 'InstrumentTypeModifier', 'LoopFunction', 
                        'LoopTagSequenceNo', 'Symbol']
    df = pd.read_csv(filepath)
    return all(col in df.columns for col in required_columns)

def validate_edges_csv(filepath):
    required_columns = ['ID', 'RunID', 'Type', 'StartNode', 'EndNode', 
                        'FlowDir', 'DrawingID', 'ItemTag']
    df = pd.read_csv(filepath)
    return all(col in df.columns for col in required_columns)

from flask import send_from_directory

# Route to serve files from the uploaded_files directory
@app.route('/uploaded_files/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


@app.route('/set_api_key', methods=['POST'])
def set_api_key():
    api_key = request.json.get('api_key')
    if api_key:
        session['api_key'] = api_key  # Store selected API key in session
        return jsonify({'status': 'success', 'message': 'API key set successfully.'})
    else:
        return jsonify({'status': 'error', 'message': 'API key is missing.'})


@app.route('/prompt')
def prompt():
    folder = request.args.get('folder')
    if not folder:
        flash('Folder not specified.')
        return redirect(url_for('upload_nodes_form'))
    
    # Check for an image file in the folder
    image_file = None
    for filename in os.listdir(folder):
        if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
            image_file = filename
            break
    
    return render_template('index3.html', folder=folder, image_file=image_file)
@app.route('/get_model_response', methods=['POST'])
def get_model_response():
    data = request.json
    prompt = data.get('prompt')
    api_key = session.get('api_key')
    
    # Call the model and get its response
    model_response = get_user_data_give_response(prompt, api_key)
    
    if model_response['result'] == 'success':
        return jsonify({'status': 'success', 'response': model_response['message']})
    else:
        return jsonify({'status': 'error', 'message': model_response['message']})



@app.route('/update_csv', methods=['POST'])
def update_csv():
    data = request.get_json()
    prompt = data.get('prompt')
    folder = data.get('folder')
    api_key = session.get('api_key')  # Retrieve the stored API key

    if not api_key:
        return jsonify({'status': 'error', 'message': 'API key not set.'})
    
    if not prompt or not folder:
        return jsonify({'status': 'error', 'message': 'Prompt or folder missing.'})

    nodes_csv = os.path.join(folder, 'csvs_nodes.csv')
    edges_csv = os.path.join(folder, 'csvs_edges.csv')

    if not os.path.exists(nodes_csv) or not os.path.exists(edges_csv):
        return jsonify({'status': 'error', 'message': 'Required CSV files not found in the specified folder.'})
    

    #count_row(nodes_csv)
    result = get_user_data_and_update_csv(prompt, nodes_csv, edges_csv,api_key)
    print(result)
    return jsonify(result)

    # try:
        
    #     count_row(nodes_csv)
    #     get_user_data_and_update_csv(prompt, nodes_csv, edges_csv)
    #     return jsonify({'status': 'success', 'message': 'CSV files updated successfully!'})
    # except Exception as e:
    #     return jsonify({'status': 'error', 'message': str(e)})

@app.route('/generate_graph', methods=['POST'])
def generate_graph():
    data = request.get_json()
    folder = data.get('folder')

    if not folder:
        return jsonify({'status': 'error', 'message': 'Folder missing.'})

    graph_filename = f'graph_{os.path.basename(folder)}.png'
    graph_output_path = os.path.join('static', 'graphs', graph_filename)

    try:
        # Generate graph
        get_graph(folder, graph_output_path)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

    if os.path.exists(graph_output_path):
        graph_url = url_for('static', filename=f'graphs/{graph_filename}')
        message = "Graph generated successfully."
        return jsonify({'status': 'success', 'graph_url': graph_url, 'message': message})
    else:
        return jsonify({'status': 'error', 'message': 'Graph was not generated.'})
    

@app.route("/handle_response_update", methods=["POST"])
def handle_response_update():
    user_response = request.json.get("response")
    if user_response.lower() == "yes":
        return jsonify({"message": "Please enter your next prompt."})
    elif user_response.lower() == "no":
        return jsonify({"message": "Thank you. Ending the session."})
    else:
        return jsonify({"message": "Invalid response. Please reply with 'yes' or 'no'."})

    
@app.route('/index3.html', methods=['GET'])
def index3():
    folder = request.args.get('folder')
    if not folder:
        flash('Folder not specified.')
    graph_filename = f'graph_{os.path.basename(folder)}.png'  # Ensure you set the correct folder variable
    graph_output_path = os.path.join('static', 'graphs', graph_filename)

    if os.path.exists(graph_output_path):
        graph_url = url_for('static', filename=f'graphs/{graph_filename}')
        return render_template('index3.html', graph_url=graph_url, folder=folder)
    else:
        return "Graph was not generated.", 404


@app.route('/process', methods=['POST'])
def process():
    folder = request.form['folder']
    # Render index3.html with the folder data for further actions
    return render_template('index3.html', folder=folder)



@app.route('/upload_another')
def upload_another():
    folder = request.args.get('folder')

    if folder and os.path.exists(folder):
        shutil.rmtree(folder)

    graph_filename = f'graph_{os.path.basename(folder)}.png'
    graph_output_path = os.path.join('static', 'graphs', graph_filename)
    if os.path.exists(graph_output_path):
        os.remove(graph_output_path)

    return redirect(url_for('upload_nodes_form'))

@app.route('/another_prompt')
def another_prompt():
    folder = request.args.get('folder')

    if not folder:
        flash('Folder not specified.')
        return redirect(url_for('upload_nodes_form'))

    graph_filename = f'graph_{os.path.basename(folder)}.png'
    graph_output_path = os.path.join('static', 'graphs', graph_filename)
    if os.path.exists(graph_output_path):
        os.remove(graph_output_path)
     # Check for an image file in the folder
    image_file = None
    for filename in os.listdir(folder):
        if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
            image_file = filename
            break
    
    return render_template('index3.html', folder=folder, image_file=image_file)



from flask import send_file
import os
import zipfile
import io

@app.route('/download_csvs')
def download_csvs():
    # Define file paths
    nodes_path = os.path.join('uploaded_files', 'csvs_nodes.csv')
    edges_path = os.path.join('uploaded_files', 'csvs_edges.csv')

    # Check if files exist
    if not os.path.exists(nodes_path):
        return "CSV nodes file not found.", 404
    if not os.path.exists(edges_path):
        return "CSV edges file not found.", 404

    # Create an in-memory zip file
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w') as zf:
        # Add nodes.csv to the zip
        zf.write(nodes_path, arcname='csvs_nodes.csv')
        
        # Add edges.csv to the zip
        zf.write(edges_path, arcname='csvs_edges.csv')

    # Move the buffer cursor to the beginning
    zip_buffer.seek(0)

    # Send the zip file as a downloadable attachment
    return send_file(zip_buffer, as_attachment=True, download_name='csv_files.zip', mimetype='application/zip')

@app.route('/download_graph')
def download_graph():
    # Path to the directory where the graph images are stored
    graph_directory = 'static/graphs/'
    
    # Get the list of files in the graph directory
    files = os.listdir(graph_directory)
    
    # Filter for image files (you can adjust the extensions as needed)
    image_files = [f for f in files if f.endswith(('.png', '.jpg', '.jpeg'))]
    
    if image_files:
        # Take the first image file found
        image_file = image_files[0]
        return send_file(os.path.join(graph_directory, image_file), as_attachment=True)
    else:
        return "No graph images found.", 404
# Function to clear directories
def clear_directories():
    # Clear uploaded_files
    upload_folder = app.config['UPLOAD_FOLDER']
    if os.path.exists(upload_folder):
        for file in os.listdir(upload_folder):
            file_path = os.path.join(upload_folder, file)
            if os.path.isfile(file_path):
                os.remove(file_path)
    
    # Clear static/graphs
    graphs_folder = os.path.join('static', 'graphs')
    if os.path.exists(graphs_folder):
        for file in os.listdir(graphs_folder):
            file_path = os.path.join(graphs_folder, file)
            if os.path.isfile(file_path):
                os.remove(file_path)

# Call the clear_directories function to remove existing files
clear_directories()

if __name__ == '__main__':
    app.run(debug=False)
