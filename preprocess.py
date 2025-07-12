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
    Converts a parent-style Excel sheet with home address info into a clean stop list.
    Expects: home address, city, zip code, school
    Returns: DataFrame with columns ['Address', 'School', 'Student ID' (optional)]
    """
    # Normalize column names
    df.columns = df.columns.str.strip().str.lower()

    required = ["home address", "city", "school"]
    for col in required:
        if col not in df.columns:
            raise ValueError(f"❌ Required column '{col}' not found in uploaded sheet.")

    # Optional zip
    zip_part = df["zip code"].astype(str).str.strip() if "zip code" in df.columns else ""

    # Combine into full geocodable address
    df["address"] = df["home address"].astype(str).str.strip() + ", " + df["city"].astype(str).str.strip()
    if "zip code" in df.columns:
        df["address"] += ", " + zip_part

    # Standardize school column
    df["school"] = df["school"].astype(str).str.strip()

    return df[["address", "school"]].dropna()
