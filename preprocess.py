# preprocess.py

import pandas as pd

def load_input_data(csv_file):
    df = pd.read_csv(csv_file)
    df.columns = df.columns.str.strip()
    # Drop rows missing key location fields
    if "Home Address" in df.columns:
        df = df.dropna(subset=["Home Address"])
    elif "lat" in df.columns and "lon" in df.columns:
        df = df.dropna(subset=["lat", "lon"])
    else:
        raise ValueError("CSV must contain either 'Home Address' or 'lat'/'lon' columns.")
    return df
