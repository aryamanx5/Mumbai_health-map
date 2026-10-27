# Power BI report: open, publish and attach to the web app

The report is a **Power BI Project** (`MumbaiHealth.pbip`). It is a folder of text files that Power BI Desktop opens like a
`.pbix`. It has five pages with a left navigation rail, a title band, KPI cards, slicers and chart cards.

The theme is built around the project's two topics rather than copied from the sample:

* **Navy frame.** A deep clinical navy for the navigation rail and the title bands, on a pale blue-grey page.
* **Heart red for cardiovascular risk.** The Model performance and Patient data pages carry a red accent line, red KPI values
  and red slicer and table headers. In charts, "Heart disease" is always red and "No heart disease" is light blue.
* **Teal for Mumbai healthcare access.** The Mumbai facilities page uses teal accents, and the facility types are shades of
  teal, navy and amber, the same on every chart and on the map.
* **Models keep fixed colours.** Logistic Regression is light blue, Random Forest red and the neural network navy, on every page.
* Each title band names its module (Module 1 · Cardiovascular risk, Module 2 · Mumbai healthcare access), and the rail
  carries a heart mark and the reminder that the clinical data is Indian, not Mumbai-specific.

| Page | What it shows |
|---|---|
| Home | KPI cards: patients, heart-disease rate, best ROC-AUC, public health sites, population, sites per 100k. Charts: test accuracy by model, facility records by category, patients by age band and outcome. Highlights |
| Model performance | Model slicer. Cards: best model, majority-class baseline, patients all three models got right. Test-metrics matrix, confusion matrix, ROC curves, test vs CV ROC-AUC, permutation importance |
| Patient data | Sex and outcome slicers. Cards: patients, heart-disease rate, average age, cholesterol not recorded. Age band × outcome, rate by chest pain, by ST slope and by major vessels, sex split |
| Mumbai facilities | Facility-type and ward slicers. Cards: sites, sites per 100k, hospitals list rows, beds. Facility map, sites per 100k by ward, records by category, beds by ownership |
| Insights | Four text panels (models, patient data, Mumbai facilities, cleaning and caveats), the cleaning log and missing values by stage |

The insight sentences are calculated from the data when the project is generated, so they match the numbers in the charts.

## 1. Open it (Windows, Power BI Desktop)

You need **Power BI Desktop** (free, from the Microsoft Store), version from 2024 or later.

1. Run `start_windows.bat` once. Among other things it runs `python -m src.powerbi_project --set-data-folder`, which points
   the report at this computer's `powerbi\data\` folder. (Or run that command yourself.)
2. In Power BI Desktop, open **File → Options and settings → Options → Preview features**. If these two options are listed,
   tick them and restart Desktop:
   * **Power BI Project (.pbip) save option**;
   * **Store reports using enhanced metadata format (PBIR)**.

   Recent versions have both on by default and no longer list them.
3. **File → Open**, choose `powerbi\MumbaiHealth.pbip`.
4. A project holds no data until it is refreshed, so the visuals start empty. Click **Home → Refresh**. Then check that the
   Home page shows 1,000 patients, 58.0%, 0.992, 402 sites, 12,442,373 people and 3.23 per 100k.

If the refresh says a file is not found, the data path is wrong. Fix it with **Home → Transform data → Edit parameters →
DataFolder**: enter the full path of the `powerbi\data\` folder, ending with a backslash (for example
`C:\Users\you\Downloads\dv\powerbi\data\`). Then click **Refresh** again.

If the map is blank, click it, and in the Visualizations pane drag `fact_facility[latitude]` into **Latitude** and
`fact_facility[longitude]` into **Longitude**. If your version of Desktop offers to switch the map to **Azure Maps**, accept.

## 2. Save it as a normal .pbix (optional)

**File → Save as → Power BI file (.pbix)** gives you a single file to hand in or email. The `.pbip` folder stays the editable
source.

## 3. Publish

1. Sign in to Power BI Desktop with your school or work account (top right).
2. **Home → Publish**, and choose **My workspace** (or a group workspace).
3. When it finishes, click **Open 'MumbaiHealth.pbix' in Power BI**.

## 4. Get the embed link

**Option A, Publish to web (public).** This is what the sample project used: anyone with the link can view the report without
signing in. Use it only because this report holds no personal data. The clinical data is a public, de-identified dataset.

1. In the Power BI service, open the report. Choose **File → Embed report → Publish to web (public)**.
2. Click **Create embed code**, then **Publish**.
3. Copy the **Link you can send in email**. It looks like `https://app.powerbi.com/view?r=eyJrIjoi...`.

If the option is greyed out, your organisation's admin has turned off Publish to web. Many university tenants do this. In that
case:

**Option B, secure embed (viewers sign in).** Choose **File → Embed report → Website or portal**, and copy the first link
(`https://app.powerbi.com/reportEmbed?reportId=...`). Viewers must sign in with an account that has access to the report.
Share it with them from the report's **Share** button.

## 5. Attach it to the web app

1. Open `dashboard\powerbi-config.js` and paste the link:

   ```js
   window.POWERBI_REPORT = {
     embedUrl: "https://app.powerbi.com/view?r=eyJrIjoi...",
     reportUrl: "",   // optional: the report's normal link, for the "Open in Power BI" button
   };
   ```

2. Save, start the app (`start_windows.bat`) and open <http://localhost:8050/dashboard/#powerbi>. The **Power BI Dashboard**
   button in the header opens the same tab. The report appears embedded, with its page navigation.

## 6. After changing the data

1. Run `python run_pipeline.py`. This rewrites the CSVs in `powerbi\data\` and keeps any edits you made to the report.
2. Refresh in Power BI Desktop, then publish again. The Publish-to-web link stays the same.

`python -m src.powerbi_project --rebuild` regenerates the whole report from code. It **overwrites** changes made in Desktop,
so only use it if you have not edited the report by hand.

## Files

| Path | What it is |
|---|---|
| `MumbaiHealth.pbip` | Open this in Power BI Desktop |
| `MumbaiHealth.SemanticModel/` | The data model in TMDL: 15 tables, 11 relationships, 35 DAX measures, and the `DataFolder` parameter |
| `MumbaiHealth.Report/` | The five pages, in the PBIR format. Theme: `StaticResources/RegisteredResources/MumbaiHealthTheme.json` |
| `data/*.csv` | The tables the report loads, written by `run_pipeline.py` |
| `measures.dax` | All measures as text, for reading or copying |

## What was checked, and what was not

* **Checked here:** the data model loads in Microsoft's own TMDL parser (`Microsoft.AnalysisServices`, the library Power BI
  uses). Every report file validates against Microsoft's published PBIR JSON schemas. Automated tests (`tests/test_powerbi.py`)
  check the following:
  * every field a visual uses exists in the model;
  * every measure reference resolves;
  * the navigation buttons point at real pages;
  * the report numbers reconcile with the pipeline.
* **Not checked here:** the report was generated on Linux, where Power BI Desktop does not run. So it has not been opened in
  Desktop yet. If a visual shows an error when you first open it, the fix is usually to re-drag its fields in the
  Visualizations pane. Please tell me what you see, and I can adjust the generator.
