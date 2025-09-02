'''
A simple example to run CDFT with background charges.
'''

from pyscf import neo
from pyscf.qmmm.mm_mole import create_mm_mol

mmcoords, mmcharges, mmradii = [], [], []
f_mm = open('x_00_mmcoords.xyz', 'r')
for line in f_mm:
    if len(line.split()) == 4:
        if line.split()[0] == 'O':
            mmcoords.append([float(x) for x in line.split()[1:4]])
            mmcharges.append(-0.82)
            mmradii.append(0.31)
        elif line.split()[0] == 'H':
            mmcoords.append([float(x) for x in line.split()[1:4]])
            mmcharges.append(0.41)
            mmradii.append(0.66)

mmmol = create_mm_mol(mmcoords, mmcharges, mmradii)

mol = neo.M(atom='x_00_coords.xyz',
            basis='6-31g',
            nuc_basis='pb4d',
            verbose=4,
            mm_mol=mmmol)

mf_nopbc = neo.CDFT(mol, xc='B3LYP')
mf_nopbc.kernel()
