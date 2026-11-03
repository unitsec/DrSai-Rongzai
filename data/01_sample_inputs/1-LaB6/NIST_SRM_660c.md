# NIST SRM 660c: Lanthanum Hexaboride Powder

## Standard information

- **Designation:** NIST Standard Reference Material (SRM) 660c
- **Material:** Lanthanum hexaboride (LaB6) powder
- **Intended use:** Calibration of diffraction-line positions and line shapes in powder diffractometry.
- **Unit of issue:** Approximately 6 g of LaB6 powder bottled under argon.
- **Isotopic composition:** Prepared using boron enriched to a nominal 99% in $^{11}\mathrm{B}$, reducing neutron absorption and making the material suitable for neutron diffraction.
- **Preparation:** Produced in a dedicated processing run, annealed, and bottled under argon.
- **Certificate issue date:** 29 October 2015
- **Period of validity:** Indefinite, provided that the material is handled and stored according to the NIST certificate and is not damaged, contaminated, or otherwise modified.

## Certified value

The certified cubic lattice parameter at $22.5\ ^\circ\mathrm{C}$ reported by NIST is:

$$
a = 0.4156826 \pm 0.000008\ \mathrm{nm}
  = 4.156826 \pm 0.000080\ \mathrm{\mathring{A}},
$$

where the uncertainty is the expanded uncertainty with coverage factor $k=2$.

NIST also reports an approximate mean volume-weighted crystalline-domain size of $0.8\ \mu\mathrm{m}$ as an information value. The microstrain term refined to zero during the certification analysis; these are information values rather than certified values.

## Local diffraction dataset

The local time-of-flight neutron powder diffraction dataset was collected using the TREND diffractometer at the China Spallation Neutron Source (CSNS), Dongguan, China. The present dataset uses the backscattering detector bank centered at $2\theta=177.0^\circ$, with a total flight path of 80.0027 m.

Relevant local files:

- `RUN0001239_groupBM.gsa`: neutron powder diffraction data
- `groupBM_2025.instprm`: GSAS-II instrument parameters
- `LaB6.cif`: starting crystal-structure model
- `description.txt`: concise sample and instrument description

## Usage note

The lattice parameter stored in `LaB6.cif` is part of the local starting structural model and is not the NIST-certified value. For metrological calibration or reporting of the certified reference value, use the value and uncertainty from the current NIST certificate.

## Official sources

- [NIST SRM 660c product page](https://shop.nist.gov/ccrz__ProductDetails?sku=660c&cclcl=en_US)
- [NIST SRM 660c certificate](https://tsapps.nist.gov/srmext/certificates/660c.pdf)
