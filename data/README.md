# Rongzai agent: raw refinement data supporting the manuscript

Raw data of the Rietveld refinements reported in *Rongzai agent: A Large Language Model-Based
Autonomous Assistant for Rietveld Refinement of Neutron Diffraction Data*: the measured patterns and
their refinement inputs, and the GSAS-II refinements produced by the agent and by the two human
specialists.

Archived release **v2-r1** - version DOI 10.5281/zenodo.23883832, concept DOI 10.5281/zenodo.23883831.
Source code: https://github.com/unitsec/DrSai-Rongzai

## Contents

| folder | contents |
| --- | --- |
| `01_sample_inputs/` | per-sample refinement inputs: measured diffraction data (`.gsa`/`.dat`),
instrument parameters (`.instprm`), crystal structure (`.cif`), `description.txt` and
reference-material notes |
| `02_agent_runs/` | one folder per agent run: `deepseek-v4-pro-agent1` ... `-agent5` (the five
repeat runs of every sample), `no-expert-knowledge` (the zero-knowledge control), `ablation`,
`temperature-sensitivity` (Si), `prompt-sensitivity` (Si) and `detector-robustness` (Si); each
folder holds the GSAS-II project (`.gpx`), its listing (`.lst`), the refined structure (`.cif`) and,
where no project file could be exported, `rwp-summary.txt` |
| `03_specialist_runs/` | the human specialists' GSAS-II projects, listings and refined structures:
`humanRefine1` and `humanRefine2` for five samples each, and `specialist_runs_in_sample_dir` for the
remaining four |
| `README.md`, `MANIFEST.csv` | this file, and a manifest listing every archived file with its size |

## Sample naming

| folder | sample |
| --- | --- |
| `0-Si` | Si (NIST SRM 640g) |
| `1-LaB6` | LaB6 (NIST SRM 660c) |
| `2-zeolite` | Zeolite |
| `3-LiNi0.9Co0.05Mn0.05O2` | NCM90, LiNi0.9Co0.05Mn0.05O2 |
| `4-NaNi0.33Mn0.33Fe0.33O2` | NFM, NaNi0.33Mn0.33Fe0.33O2 |
| `5-BaFeO3` | BaFeO3 |
| `6-BaCO3` | BaCO3 |
| `7-Y2O3` | Y2O3 |
| `8-Y2O3-BaCO3` | Y2O3-BaCO3 |

## The three prompt variants (`0-Si/prompt-sensitivity`)

`prompt-1-refine-with-gsasii` = ``please refine this neutron powder diffraction data with GSAS-II'';
`prompt-2-refine-uploaded-data` = ``refine the neutron powder diffraction data I uploaded with
GSAS-II''; `prompt-3-gsas-refinement` = ``carry out a GSAS refinement of the neutron powder
diffraction data I uploaded''.

## How to inspect the refinements

Open any `.gpx` file in GSAS-II to see the full refinement: the parameter history, the observed,
calculated and difference patterns, and the agreement factors of the final step. The matching `.lst`
file is the plain-text GSAS-II listing of the same refinement, and the refined structure is exported
as `.cif`.

## Notes

- Intermediate GSAS-II backups (`*.bak0.gpx`, ...) were not archived; the project files of every run
  are included.
- The patterns were measured at CSNS (MPI, TREND) and ISIS (POLARIS); please cite the original
  facility data sources when reusing the raw patterns.

## Citation

If you use these data, please cite the manuscript and this archived release
(DOI 10.5281/zenodo.23883832).
