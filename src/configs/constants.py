from pathlib import Path
here = Path(__file__).parent.resolve()

# file save path
files_dir = str(here.parent.parent /'files')
# print(files_dir)

tools_dir = str(here.parent.parent/'tools')