# Installation Guide

## Quick Start

```bash
# Clone repository
git clone https://github.com/YOUR-USERNAME/cmt-yield-curve-bootstrap.git
cd cmt-yield-curve-bootstrap

# Install dependencies
pip install -r requirements.txt

# Run visualization
python -m streamlit run scripts/yield_curve_app.py
```

---

## Troubleshooting

### Issue: "streamlit: command not found"

**Symptoms:**
```
streamlit run scripts/yield_curve_app.py
'streamlit' is not recognized as an internal or external command
```

**Solution 1: Use python -m (Recommended)**
```bash
python -m streamlit run scripts/yield_curve_app.py
```

This bypasses PATH issues by running streamlit as a Python module.

**Solution 2: Add to PATH (Windows)**

**PowerShell (as Administrator):**
```powershell
$env:PATH += ";C:\Users\YOUR-USERNAME\AppData\Roaming\Python\Python314\Scripts"
```

**Command Prompt (as Administrator):**
```cmd
setx PATH "%PATH%;C:\Users\YOUR-USERNAME\AppData\Roaming\Python\Python314\Scripts"
```

**Solution 3: Add to PATH (macOS/Linux)**

Add to `~/.bashrc` or `~/.zshrc`:
```bash
export PATH="$HOME/.local/bin:$PATH"
```

Then:
```bash
source ~/.bashrc  # or source ~/.zshrc
```

---

## System Requirements

**Python:** 3.10 or higher
**Operating System:** Windows, macOS, Linux

**Dependencies:**
- NumPy 2.0+
- Pandas 2.0+
- Plotly 5.0+
- Streamlit 1.20+
- SciPy 1.9+
- openpyxl 3.0+

**Disk Space:**
- Code: ~5 MB
- Sample data: ~60 MB
- Full dataset (if generated): ~500 MB

---

## Installation Methods

### Method 1: pip (Recommended)

```bash
pip install -r requirements.txt
```

### Method 2: conda

```bash
conda create -n yield-curve python=3.11
conda activate yield-curve
pip install -r requirements.txt
```

### Method 3: venv

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

---

## Verification

Test your installation:

```bash
# Check versions
python -c "import numpy; print(f'NumPy: {numpy.__version__}')"
python -c "import streamlit; print(f'Streamlit: {streamlit.__version__}')"

# Run app
python -m streamlit run scripts/yield_curve_app.py
```

**Expected:** Browser opens to http://localhost:8501 with the app running

---

## Common Issues

### NumPy Version Error

**Error:** `AttributeError: module 'numpy' has no attribute 'trapz'`

**Fix:** Upgrade NumPy
```bash
pip install --upgrade numpy
```

### Pandas Compatibility

**Error:** `AttributeError: 'TimedeltaIndex' object has no attribute 'dt'`

**Fix:** Already fixed in latest code. Pull latest version.

### Missing NPZ Files

**Error:** "No NPZ files found!"

**Fix:** Sample files should be in `data/samples/`. If missing:
```bash
# Check if samples directory exists
ls data/samples/

# If empty, download from GitHub release or run bootstrap
python src/cmt_bootstrap.py --scheme 2 --write-npz
```

---

## Performance Tips

**Slow Tab 3 (Forward Projections):**
- Default selection: 1Mo, 1Yr, 5Yr (3 tenors)
- Avoid selecting all 9 tenors simultaneously
- Cross-section view is optional (off by default)

**Large Datasets:**
- Full 1990-2026 dataset: ~300MB (S3)
- For faster loading, use date-filtered NPZ files
- Sample data (2022-2026) is recommended for exploration

---

## Development Setup

For contributing:

```bash
# Clone repository
git clone https://github.com/YOUR-USERNAME/cmt-yield-curve-bootstrap.git
cd cmt-yield-curve-bootstrap

# Create development environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run tests (if available)
# python -m pytest tests/

# Run app in debug mode
streamlit run scripts/yield_curve_app.py --logger.level=debug
```

---

## Uninstallation

```bash
# Remove virtual environment
deactivate
rm -rf venv

# Or uninstall packages
pip uninstall -r requirements.txt -y
```

---

## Getting Help

**Issues:** https://github.com/NaraSiva90/CMTRateBootstrap/issues
**Discussions:** https://github.com/NaraSiva90/CMTRateBootstrap/discussions
**Email:** narayanansivasailam@gmail.com

