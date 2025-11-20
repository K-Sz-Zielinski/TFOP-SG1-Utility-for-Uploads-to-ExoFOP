# TFOP SG1 Utility for Uploads to ExoFOP

Command-line tool that validates filenames, builds observation summaries, and uploads summaries & observation files to ExoFOP.

If you encounter any issues, contact me at **krzysztof.sz.zielinski@gmail.com**.

This tool was created by the owner of this repository and is an expanded and reworked version of an earlier script developed by Thiam-Guan Tan.

---

### Getting the script
Download `sg1_utility.py` and place it anywhere, e.g. `/home/user/sg1_utility.py`.

### Requirements
- Python (3.8+),
- packages: `numpy`, `astropy`, `requests` (install using `pip install numpy astropy requests`),
- valid ExoFOP account with TFOP WG credentials.

---

## Quickstart

For simplicity, all parameters must be passed as strings (quoted).

#### Single filter observations:
```bash
python /home/user/sg1_utility.py   --username "YOUR_USERNAME"   --password "YOUR_PASSWORD"   --tic "12345678.01"   --toi "1234.01"   --directory "/home/you/TOI-1234/files"   --coverage "Full"   --telsize "1.0"   --camera "CAMERA_NAME"   --psf "3.1"   --deltamag "5.0"
```
In single-filter runs `--psf` and `--deltamag` are required. Set `--deltamag "0"` to upload a blank value.

#### Multiple filters in one directory (for observing runs with alternating filters):
```bash
python /home/user/sg1_utility.py   --username "YOUR_USERNAME"   --password "YOUR_PASSWORD"   --tic "12345678.01"   --toi "1234.01"   --directory "/home/you/TOI-1234/files"   --coverage "Ingress"   --telsize "1.0"   --camera "CAMERA_NAME"
```
When multiple filters are detected the tool **prompts per filter** for PSF and Faintest-neighbor Δmag. In this multi-filter mode, any previously passed `--psf` or `--deltamag` values are ignored.

#### Dry run (validate only; no uploads):
```bash
python /home/user/sg1_utility.py   --username "YOUR_USERNAME"   --password "YOUR_PASSWORD"   --tic "12345678.01"   --toi "1234.01"   --directory "/home/you/TOI-1234/files"   --coverage "Full"   --telsize "1.0"   --camera "CAMERA_NAME"   --psf "3.1"   --deltamag "0"   --skip-summary   --skip-files
```

---

## Arguments

| Flag | Required? | Description |
|---|:--:|---|
| `--username` | ✓ | ExoFOP username |
| `--password` | ✓ | ExoFOP password |
| `--tic` | ✓ | TIC with planet index, e.g. `"12345678.01"` |
| `--toi` | ✓ | TOI with planet index, e.g. `"1234.01"`; use `"0"` if the corresponding TOI ID does not exist (some TESS exoplanet candidates do not have valid TOI identifiers) |
| `--directory` | ✓ | Path to files, e.g. `"/path/to/dir"` |
| `--coverage` | ✓ | `"Full"`, `"Ingress"`, `"Egress"`, `"Out of Transit"` |
| `--telsize` | ✓ | Telescope aperture in meters, e.g. `"0.35"` |
| `--camera` | ✓ | Camera name |
| `--psf` | ✓ | Required only for single-filter runs; string containing a numeric value |
| `--deltamag` | ✓ | Required only for single-filter runs; `"0"` means upload blank |
| `--notes` |  | Public notes (merged with auto notes if any) |
| `--skip-summary` |  | Skip time-series summary upload |
| `--skip-files` |  | Skip file uploads |

The upload group is fixed to `"tfopwg"` and cannot be changed via CLI or function arguments. Proprietary period is always enabled and fixed to 12 months.

**Skip flags**

| `--skip-summary` | `--skip-files` | Behavior |
|:--:|:--:|---|
| off | off | One confirmation → upload summary and files |
| on  | off | One confirmation → upload files only |
| off | on  | One confirmation → upload summary only |
| on  | on  | No uploads; validation/preview only |

---

## File recognition and rules

### Filenaming pattern (strict)
```
TIC<digits>-<pp>_<YYYYMMDD>_<Observatory>_<Filter>[_<N>px]_<filetype>
```
- `<digits>` is the TESS Input Catalog (TIC) identifier of the object.
- `<pp>` is the 2-digit planet index and must match both `--tic`, and `--toi` (if `--toi` is not set to "0").
- Exactly one date (`<YYYYMMDD>`) and one observatory (`<Observatory>`) across the folder.
- `<YYYYMMDD>` is the UT date of the observation.
- `<Observatory>` is the observatory abbreviation/code (e.g., `LCO-1m0-CTIO`)
- `_Npx` (optional) is the corresponding aperture radius; it is allowed if the user prepared the same type of file for more than one aperture radius.
- `<filetype>` is the information on the purpose and type of the file (e.g., `_seeing-profile.png`).

### Required per filter
- `_measurements.tbl` → **AstroImageJ Photometry Measurement Table**
- `_measurements.plotcfg` → **AstroImageJ Plot Configuration File**
- `_measurements.radec` → **AstroImageJ Photometry Aperture File**
- `_compstar-lightcurves.png` → **Compstar Light Curve Plots**
- `_field.png` → **Field Image with Apertures**
- `_field-zoom.png` → **Zoomed-in FOV**
- `_seeing-profile.png` → **Seeing Profile**
- `_WCS.fits` → **Plate-Solved Image**

### Required global
- Exactly one `_notes.txt` → **Notes and Results Text**

### Optional per filter
- `_lightcurve.png` → **Light Curve Plot**
- `_measurements_NEB-table.txt` → **NEB Table**
- `_measurements_NEBcheck.zip` → **NEB Depth Plots**
- `_measurements_dmagRMS-plot.png` → **Δmag vs. RMS Plot**
- `_subset.csv` → **Photometry Table Subset for Joint Fitting**

---

### Computations and selection
- **Primary AIJ table per filter**: among all `_measurements.tbl` candidates, pick the one with the largest median `Source_Radius`; if tied, prefer a table where the radius varies; then by largest `_Npx`; then by filename.
- **Aperture radius**: median of `Source_Radius`, rounded to 0.1 px. If the radius varies, the phrase `aperture radius was variable in time` is appended to notes.
- **Pixel scale**: mean of `proj_plane_pixel_scales(WCS)` in arcsec/pixel from the Plate-Solved Image.
- **Duration**: from first/last `JD_UTC` ± half the respective exposure (`EXPTIME` or `EXPOSURE`); minutes rounded to nearest integer.
- **Counts**: number of rows in the AIJ table.

### Upload behavior
- A single confirmation precedes any uploads.
- Per filter, a time-series summary is posted, then files are uploaded in a fixed order. The chosen `_measurements.tbl` uploads first, then any other `_measurements.tbl`, then other file types.
- All values are sent as strings, preserving the user’s input form.
- The **group** used for uploads is always `"tfopwg"`.

### PSF and Δmag logic
- **Single filter**: `--psf` and `--deltamag` are required. If `--deltamag "0"`, the ExoFOP field is left blank.
- **Multiple filters**: `--psf` and `--deltamag` on the CLI are ignored. The tool prompts per filter. Blank Δmag input leaves the field blank.

### Output preview
- Prints detected date, observatory, and filters.
- Prints **per-filter** recognized files and reasons for any rejections.
- Prints missing required/optional items per filter; for multi-filter runs, also prints a global note for `_notes.txt`.

---

## Import as a module
```python
from sg1_utility import upload

upload(
  username="YOUR_USERNAME",
  password="YOUR_PASSWORD",
  tic="12345678.01",
  toi="1234.01",
  directory="/path/to/files",
  coverage="Full",
  telsize="0.35",
  camera="QHY600M",
  psf="3.2",
  deltamag="0",
  notes=None,
  skip_summary=False,
  skip_files=False
)
```
