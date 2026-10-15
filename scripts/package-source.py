"""Create a reproducible source bundle from the public-file inventory."""
from public_files import ROOT, public_files
from release import version, write_zip

output = ROOT / "dist" / ("coindex-" + version() + "-source.zip")
write_zip(output, public_files(), ROOT, "coindex")
print(output)
