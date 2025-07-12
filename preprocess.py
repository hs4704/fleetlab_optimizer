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
    df.columns = df.columns.str.strip().str.lower()
    original_cols = df.columns.tolist()

    # Define expected field aliases
    column_aliases = {
        "address": ["home address", "street address", "addr", "address"],
        "city": ["city", "town"],
        "zip": ["zip", "zipcode", "zip code", "postal code"],
        "school": ["school", "school name", "campus"],
        "grade": ["grade", "class"],
        "transport_option": ["transportation option", "transport", "transport option", "ride option"],
        "group_pref": ["group stop", "preferred group stop", "preferred location"]
    }

    # Match columns to internal names
    mapped_cols = {}
    for canonical, aliases in column_aliases.items():
        match = next(
            (col for alias in aliases for col in original_cols if alias in col), None
        )
        if not match:
            closest = difflib.get_close_matches(canonical, original_cols, n=1)
            match = closest[0] if closest else None
        if match:
            mapped_cols[match] = canonical

    df = df.rename(columns=mapped_cols)

    # Check for required fields
    required = ["address", "city", "zip", "school"]
    missing = [r for r in required if r not in df.columns]
    if missing:
        raise ValueError(f"❌ Required column(s) missing: {', '.join(missing)}")

    # Construct full address string
    df["Address"] = df["address"].fillna("") + ", " + df["city"].fillna("") + ", " + df["zip"].fillna("")

    # Normalize school column
    df["School"] = df["school"].astype(str).str.strip()

    return df
