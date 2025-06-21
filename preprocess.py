#===Cleans and validates uploaded CSV data ===

import pandas as pd

def load_input_data(csv_file):
    df = pd.read_csv(csv_file)
    df.columns = df.columns.str.strip()
    return df.dropna(subset=["Home Address"], errors="ignore")
