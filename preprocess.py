# preprocess.py

import pandas as pd
import difflib
import streamlit as st

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
    # Normalize column names for matching
    original_cols = df.columns.tolist()
    df.columns = df.columns.str.strip().str.lower()

    st.info(f"📋 Normalized columns: {df.columns.tolist()}")

    # Common aliases for each field
    column_aliases = {
        "address": ["home address", "address", "street", "addr"],
        "city": ["city", "town"],
        "zip": ["zip", "zipcode", "zip code", "postal code"],
        "school": ["school", "school name", "campus"],
    }

    matched = {}

    # Match normalized column names to expected fields
    for key, aliases in column_aliases.items():
        for alias in aliases:
            for col in df.columns:
                if alias in col:
                    matched[key] = col
                    break
            if key in matched:
                break

    st.info(f"🔍 Matched columns: {matched}")

    # Check required fields
    required = ["address", "city", "zip", "school"]
    missing = [r for r in required if r not in matched]
    if missing:
        st.error(f"❌ Required column(s) missing: {', '.join(missing)}")
        raise ValueError(f"Missing column(s): {', '.join(missing)}")

    # Create combined Address field
    df["Address"] = (
        df[matched["address"]].fillna("").astype(str)
        + ", "
        + df[matched["city"]].fillna("").astype(str)
        + ", "
        + df[matched["zip"]].fillna("").astype(str)
    )

    # Create final School column
    df["School"] = df[matched["school"]].astype(str).str.strip()

    # Optionally clean extra whitespace from Address
    df["Address"] = df["Address"].str.replace(r"\s+", " ", regex=True).str.strip()
    st.write("✅ Columns after processing:", df.columns.tolist())
    st.write("🧪 Sample 'School' values:", df['School'].dropna().unique().tolist())

    return df

