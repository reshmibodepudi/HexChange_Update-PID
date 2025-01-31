
# Instructions to Run the Code

## 1. Set up Your Project Folder

Create your project folder as mentioned in your project setup instructions.

---

## 2. Create a Virtual Environment

To create a virtual environment, use the following command:

```bash
python -m venv venv
```

If an old virtual environment exists, it’s recommended to remove it and create a new one. To remove the old `venv`, use this command:

```bash
Remove-Item -Recurse -Force venv
```

---

## 3. Activate the Virtual Environment

Activate your virtual environment with the following command:

```bash
venv\Scripts\activate
```

---

## 4. Install the Dependencies

Install the required dependencies via `requirements.txt`:

```bash
pip install -r requirements.txt
```

If you encounter issues installing dependencies, try installing them one by one using these commands:

```bash
pip install pandas
pip install flask
pip install python-dotenv
pip install matplotlib
pip install openai
pip install google-generativeai
pip install networkx
```

---

## 5. Run the Application

Once your environment is set up, run the app with the following command:

```bash
python app.py
```

---

## 6. Python Version

Ensure that your Python version is below 3.13. The recommended version is 3.12.3.

---

## 7. Upload Folder Requirements

When uploading a folder, it should contain the following files:
- `nodes.csv`
- `edges.csv`
- `pid image`

---

## 8. Create the `.env` File

You need to create a `.env` file in the root directory of your project to store your API keys and Flask secret key. Below is the format you should follow for the `.env` file:

### For Gemini API

```env
API_KEY='your_gemini_api_key'
```

---

### For OpenAI API

```env
api='your_openai_api_key'
```

---

### For Flask Secret Key

```env
SECRET_KEY='supersecretkey123!'
```

---

### For Azure OpenAI API

```env
AZURE_OAI_ENDPOINT='your_azure_openai_api_endpoint'
AZURE_OAI_KEY='your_azure_openai_api_key'
AZURE_OAI_DEPLOYMENT='your_azure_openai_deployment_model'
```

---

With this, your environment should be ready for running the code.