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
def preprocess_excel_style_sheet(df):
    """
    Converts Excel-style address sheet into stop-level format.
    Combines Home Address, City, and Zip into a single Address string.
    Removes duplicates and unnecessary columns.
    """
    if not all(col in df.columns for col in ["Home Address", "City", "Zip Code", "School"]):
        raise ValueError("Missing required columns: Home Address, City, Zip Code, or School")

    df["Address"] = (
        df["Home Address"].astype(str).str.strip()
        + ", " + df["City"].astype(str).str.strip()
        + " " + df["Zip Code"].astype(str).str.strip()
    )

    df_out = df[["Address", "School"]].drop_duplicates()
    df_out = df_out.rename(columns={"School": "School Name"})

    return df_out
