#!/usr/bin/env bash
set -euo pipefail


# nohup conda run -n gsas2_py311 --live-stream python $PWD/tools/GSAS-II-master/GSASII/0neutron_gsas_refine.py > output_gsas_refine.log 2>&1 &

# nohup conda run -n diffpy.pdffit2_env --live-stream python $PWD/tools/pdf_refinement/0pdf_refine.py > output_pdf_refine.log 2>&1 &
# ps -ef | grep python
if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
	# shellcheck disable=SC1091
	source "$HOME/miniconda3/etc/profile.d/conda.sh"
elif [[ -f "$HOME/anaconda3/etc/profile.d/conda.sh" ]]; then
	# shellcheck disable=SC1091
	source "$HOME/anaconda3/etc/profile.d/conda.sh"
elif command -v conda >/dev/null 2>&1; then
	eval "$(conda shell.bash hook)"
else
	echo "[error] conda not found. Please install conda and initialize shell first."
	exit 1
fi

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

conda activate gsas2_py311
nohup python "$PROJECT_ROOT/tools/GSAS-II-master/GSASII/0neutron_gsas_refine.py" > "$PROJECT_ROOT/output_gsas_refine.log" 2>&1 &

echo "Tool services started. Check logs in project root (output_*.log)."