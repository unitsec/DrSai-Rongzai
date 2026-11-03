# NIST SRM 640g: Silicon Powder

## Standard information

- **Designation:** NIST Standard Reference Material (SRM) 640g
- **Material:** Silicon powder
- **Intended use:** Calibration of powder diffraction equipment with respect to diffraction-line position and profile breadth as a function of scattering angle.
- **Unit of issue:** Approximately 7.5 g of silicon powder bottled under argon.
- **Certificate issue date:** 27 February 2024
- **Period of validity:** Indefinite, provided that the material is handled and stored according to the NIST certificate and is not damaged, contaminated, or otherwise modified.

## Certified value

The certified cubic lattice parameter reported by NIST is:

$$
a = 0.5431109 \pm 0.0000080\ \mathrm{nm}
  = 5.431109 \pm 0.000080\ \mathrm{\mathring{A}},
$$

where the uncertainty is the expanded uncertainty with coverage factor $k=2$.

## Local diffraction dataset

The local time-of-flight neutron powder diffraction dataset was collected using the Multi-Physics Instrument (MPI) at the China Spallation Neutron Source (CSNS), Dongguan, China. The present dataset uses detector Bank 5, centered at $2\theta=95.0^\circ$, with a total flight path of 30.0 m.

Relevant local files:

- `RUN0023568_group5.gsa`: neutron powder diffraction data
- `RT_group5.instprm`: GSAS-II instrument parameters
- `Si.cif`: starting crystal-structure model
- `description.txt`: concise sample and instrument description

## Usage note

The lattice parameter stored in `Si.cif` is part of the local starting structural model and is not the NIST-certified value. For metrological calibration or reporting of the certified reference value, use the value and uncertainty from the current NIST certificate.

## Official sources

- [NIST SRM 640g product page](https://shop.nist.gov/ccrz__ProductDetails?sku=640g&cclcl=en_US)
- [NIST SRM 640g certificate](https://tsapps.nist.gov/srmext/certificates/640g.pdf)
