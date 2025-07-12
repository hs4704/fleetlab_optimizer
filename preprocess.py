# preprocess.py

import pandas as pd
import difflib

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
    

    # Normalize column names
    original_cols = df.columns.tolist()
    df.columns = df.columns.str.strip().str.lower()

    # DEBUG: Show columns after normalization
    st.info(f"📋 Normalized columns: {df.columns.tolist()}")

    # Aliases for matching expected fields
    column_aliases = {
        "address": ["home address", "address", "street", "addr"],
        "city": ["city", "town"],
        "zip": ["zip", "zipcode", "zip code", "postal code"],
        "school": ["school", "school name", "campus"],
    }

    matched = {}

    # Try to match each expected field
    for key, aliases in column_aliases.items():
        for alias in aliases:
            for col in df.columns:
                if alias in col:
                    matched[key] = col
                    break
            if key in matched:
                break

    # DEBUG: Show mapping
    st.info(f"🔍 Matched columns: {matched}")

    # Check required fields
    required = ["address", "city", "zip", "school"]
    missing = [r for r in required if r not in matched]
    if missing:
        raise ValueError(f"❌ Required column(s) missing: {', '.join(missing)}")

    # Build standard Address column
    df["Address"] = (
        df[matched["address"]].fillna("").astype(str)
        + ", "
        + df[matched["city"]].fillna("").astype(str)
        + ", "
        + df[matched["zip"]].fillna("").astype(str)
    )

    # Rename school column
    df["School"] = df[matched["school"]].astype(str).str.strip()

    return df
