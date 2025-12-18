# Global City Light Analysis

This project analyzes nighttime light data (VIIRS) using Google Earth Engine to compare the luminosity of various cities and their capitals.

## Prerequisites

- **Python 3.x** installed on your system.
- A **Google Cloud Project** with the **Earth Engine API** enabled.
  - You can create a project and enable the API at [https://console.cloud.google.com/](https://console.cloud.google.com/).
  - Make sure your user account has access to this project.

## Installation

1.  **Clone the repository** (or navigate to the project directory):
    ```bash
    cd /path/to/light_analysis
    ```

2.  **Create a virtual environment**:
    ```bash
    python3 -m venv venv
    ```

3.  **Activate the virtual environment**:
1.  Clone the repository.
2.  Install the required Python packages:
    ```bash
    pip install earthengine-api pandas python-dotenv
    ```
3.  Authenticate with Earth Engine:
    ```bash
    earthengine authenticate
    ```

## Configuration

1.  **Environment Variables**: Create a `.env` file in the project root and add your Google Cloud Project ID:
    ```
    PROJECT_ID=your-project-id
    ```
    (Or set the `GOOGLE_CLOUD_PROJECT` environment variable).

2.  **City Data**: The list of cities to analyze is stored in `targets.json`. You can modify this file to add or remove cities. The format is:
    ```json
    {
        "CountryName": {
            "Capital": [Lat, Lon],
            "City_Name": "Name",
            "City": [Lat, Lon],
            "Radius": 50,       // Optional: Override city search radius (km)
            "Cap_Radius": 50    // Optional: Override capital search radius (km)
        }
    }
    ```
    (See `example.targets.json` for a template).

3.  **Script Parameters**: You can adjust the `YEAR` and `RADIUS` constants at the top of `analyze_lights.py` if needed.

## Usage

Run the script:
```bash
python analyze_lights.py
```

The script will initialize Earth Engine using the project ID from your `.env` file and begin processing the cities listed in `targets.json`.

## Output

The script prints the analysis results to the console, showing:
- **COUNTRY**: Name of the country.

- **CITY**: Name of the city.
- **POP(Strict)**: Population living on "Built-up" (concrete) pixels. Good for density checks.
- **POP(Metro)**: Population living within 2km of built-up areas. Better for total metro area count.
- **CITY SOL**: Sum of Lights for the city (Built-up area).
- **AREA km2**: Built-up area of the city in square kilometers.
- **CAP SOL**: Sum of Lights for the capital.
- **CAP POP(S)**: Capital Population (Strict).
- **CAP POP(M)**: Capital Population (Metro).
- **DIST km**: Distance between the city and the capital (km).
- **% of CAP**: The ratio of City Light to Capital Light.
- **LIGHT/CAP**: Light Intensity per Capita (False Positive Check).
  - Normal cities: ~0.05 - 0.5
  - Industrial city or port: ~0.5 - 1.0
  - Industrial/Oil sites: > 1.0

### CSV Export
The script also saves the full results to `light_analysis_results.csv` in the same directory.

## Data Sources

- **Nighttime Lights**: NOAA VIIRS DNB Monthly Composites (Year: 2023, Configurable).
- **Population**: WorldPop Global Project Population Data (Year: 2020).
- **Land Cover**: ESA WorldCover v200 (Year: 2021).
