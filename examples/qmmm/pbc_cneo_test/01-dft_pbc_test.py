#!/usr/bin/env python
#
# Author: Qiming Sun <osirpt.sun@gmail.com>
#

'''
A simple example to run HF with background charges.
'''

import numpy
from pyscf import gto, dft
from pyscf.scf import RHF
from pyscf.qmmm.pbc.itrf import add_mm_charges
from pyscf.qmmm.itrf import mm_charge

mol = gto.M(atom='x_00_coords.xyz',
            basis='3-21g',
            verbose=4)
print(mol.atom_coords())

coords, charges = [], []
f_mm = open('x_00_mmcoords.xyz', 'r')
for line in f_mm:
    if len(line.split()) == 4:
        if line.split()[0] == 'O':
            coords.append([float(x) for x in line.split()[1:4]])
            charges.append(-0.82)
        elif line.split()[0] == 'H':
            coords.append([float(x) for x in line.split()[1:4]])
            charges.append(0.41)

# numpy.random.seed(1)
# coords = numpy.random.random((5,3)) * 10
# charges = (numpy.arange(5) + 1.) * -.1
coords = numpy.array(coords)
charges = numpy.array(charges)
print(coords.shape)
print(charges.shape)

a = numpy.eye(3) * 40
# print(a)
mf = dft.RKS(mol)#, xc='pbe')

print(type(mf))
mf = add_mm_charges(mf, coords, a, charges)
print(type(mf))
mf.kernel()

# mf_nopbc = mm_charge(mf, coords, charges)
# print(type(mf_nopbc))
# mf_nopbc.kernel()
