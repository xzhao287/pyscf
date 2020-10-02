#!/usr/bin/env python

'''
Nuclear Electronic Orbital Hartree-Fock (NEO-HF)
'''

import numpy
from pyscf import gto
from pyscf import scf
from pyscf import lib
from pyscf.lib import logger
from pyscf.scf import rhf
from pyscf.scf.hf import SCF

def init_guess_mixed(mol, mixing_parameter = numpy.pi/4):
    ''' Generate density matrix with broken spatial and spin symmetry by mixing
    HOMO and LUMO orbitals following ansatz in Szabo and Ostlund, Sec 3.8.7.
    
    psi_1a = numpy.cos(q)*psi_homo + numpy.sin(q)*psi_lumo
    psi_1b = numpy.cos(q)*psi_homo - numpy.sin(q)*psi_lumo
        
    psi_2a = -numpy.sin(q)*psi_homo + numpy.cos(q)*psi_lumo
    psi_2b =  numpy.sin(q)*psi_homo + numpy.cos(q)*psi_lumo

    Returns: 
        Density matrices, a list of 2D ndarrays for alpha and beta spins
    '''
    # opt: q, mixing parameter 0 < q < 2 pi
    
    #based on init_guess_by_1e
    h1e = scf.hf.get_hcore(mol)
    s1e = scf.hf.get_ovlp(mol)
    mo_energy, mo_coeff = rhf.eig(h1e, s1e)
    mf = scf.HF(mol)
    mo_occ = mf.get_occ(mo_energy=mo_energy, mo_coeff=mo_coeff)

    homo_idx=0
    lumo_idx=1

    for i in range(len(mo_occ)-1):
        if mo_occ[i]>0 and mo_occ[i+1]<0:
            homo_idx=i
            lumo_idx=i+1

    psi_homo=mo_coeff[:, homo_idx]
    psi_lumo=mo_coeff[:, lumo_idx]
    
    Ca=numpy.zeros_like(mo_coeff)
    Cb=numpy.zeros_like(mo_coeff)


    #mix homo and lumo of alpha and beta coefficients
    q=mixing_parameter

    for k in range(mo_coeff.shape[0]):
        if k == homo_idx:
            Ca[:,k] = numpy.cos(q)*psi_homo + numpy.sin(q)*psi_lumo
            Cb[:,k] = numpy.cos(q)*psi_homo - numpy.sin(q)*psi_lumo
            continue
        if k==lumo_idx:
            Ca[:,k] = -numpy.sin(q)*psi_homo + numpy.cos(q)*psi_lumo
            Cb[:,k] =  numpy.sin(q)*psi_homo + numpy.cos(q)*psi_lumo
            continue
        Ca[:,k]=mo_coeff[:,k]
        Cb[:,k]=mo_coeff[:,k]

    dm =scf.UHF(mol).make_rdm1( (Ca,Cb), (mo_occ,mo_occ) )
    return dm 



class HF(SCF):
    '''Hartree Fock for NEO
    
    Example:
    
    >>> from pyscf import neo
    >>> mol = neo.Mole()
    >>> mol.build(atom = 'H 0 0 0; F 0 0 0.917', basis = 'ccpvdz')
    >>> mf = neo.HF(mol)
    >>> mf.scf()
    
    '''

    def __init__(self, mol, restrict = True):
        SCF.__init__(self, mol)

        self.mol = mol
        self.dm_elec = None
        self.dm_nuc = [None]*self.mol.nuc_num
        self.verbose = 4

        # set up the Hamiltonian for electrons
        self.restrict = restrict
        if restrict == True:
            self.mf_elec = scf.RHF(self.mol.elec)
        else:
            self.mf_elec = scf.UHF(self.mol.elec)
            #self.dm0_elec = init_guess_mixed(self.mol.elec)

        self.dm0_elec = self.mf_elec.get_init_guess(key='atom')
        self.mf_elec.get_hcore = self.get_hcore_elec

    def get_hcore_nuc(self, mole):
        'get the core Hamiltonian for quantum nucleus.'

        i = mole.atom_index
        mass = 1836.15267343 * self.mol.mass[i] # the mass of quantum nucleus in a.u.

        h = mole.intor_symmetric('int1e_kin')/mass
        h -= mole.intor_symmetric('int1e_nuc')*self.mol._atm[i,0] # times nuclear charge

        # Coulomb interactions between quantum nucleus and electrons
        if isinstance(self.dm_elec, numpy.ndarray):
            if self.restrict == False: # unrestricted case
                h -= scf.jk.get_jk((mole, mole, self.mol.elec, self.mol.elec), self.dm_elec[0], scripts='ijkl,lk->ij', aosym ='s4') * self.mol._atm[i,0]
                h -= scf.jk.get_jk((mole, mole, self.mol.elec, self.mol.elec), self.dm_elec[1], scripts='ijkl,lk->ij', aosym ='s4') * self.mol._atm[i,0]
            else:
                h -= scf.jk.get_jk((mole, mole, self.mol.elec, self.mol.elec), self.dm_elec, scripts='ijkl,lk->ij', aosym ='s4') * self.mol._atm[i,0]

        # Coulomb interactions between quantum nuclei
        for j in range(len(self.dm_nuc)):
            k = self.mol.nuc[j].atom_index
            if k != i and isinstance(self.dm_nuc[j], numpy.ndarray):
                h += scf.jk.get_jk((mole, mole, self.mol.nuc[j], self.mol.nuc[j]), self.dm_nuc[j], scripts='ijkl,lk->ij') * self.mol._atm[i, 0] * self.mol._atm[k, 0] # times nuclear charge

        return h

    def get_occ_nuc(self, nuc_energy=None, nuc_coeff=None):
        'label the occupation for quantum nucleus'

        e_idx = numpy.argsort(nuc_energy)
        e_sort = nuc_energy[e_idx]
        nuc_occ = numpy.zeros(nuc_energy.size)
        #nocc = self.mol.nuc_num
        nocc = 1
        nuc_occ[e_idx[:nocc]] = 1

        return nuc_occ

    def get_init_guess_nuc(self, mole, key=None):
        '''Generate initial guess density matrix for quantum nuclei from core hamiltonian

           Returns:
            Density matrix, 2D ndarray
        '''
        h1n = self.get_hcore_nuc(mole)
        s1n = mole.intor_symmetric('int1e_ovlp')
        nuc_energy, nuc_coeff = scf.hf.eig(h1n, s1n)
        nuc_occ = self.get_occ_nuc(nuc_energy, nuc_coeff)

        return scf.hf.make_rdm1(nuc_coeff, nuc_occ)
    
    def get_hcore_elec(self, mole=None):
        'Get the core Hamiltonian for electrons in NEO'
        if mole == None:
            mole = self.mol.elec # the Mole object for electrons in NEO

        j = 0
        # Coulomb interactions between electrons and all quantum nuclei
        for i in range(len(self.dm_nuc)):
            if isinstance(self.dm_nuc[i], numpy.ndarray):
                j -= scf.jk.get_jk((mole, mole, self.mol.nuc[i], self.mol.nuc[i]), self.dm_nuc[i], scripts='ijkl,lk->ij', intor='int2e', aosym='s4') * self.mol._atm[self.mol.nuc[i].atom_index, 0]

        return scf.hf.get_hcore(mole) + j

    def get_veff_nuc_bare(self, mol, dm, dm_last=None, vhf_last=None, hermi=1, vhfopt=None):
        'NOTE: Only for single quantum proton system.'
        return numpy.zeros((mol.nao_nr(), mol.nao_nr()))

    def get_veff_nuc(self, mol, dm, dm_last=None, vhf_last=None, hermi=1, vhfopt=None):
        'get the HF effective potential for quantum nuclei in NEO'

        Z2 = self.mol._atm[mol.atom_index, 0]**2

        if dm_last is None:
            vj, vk = scf.jk.get_jk(mol, (dm, dm), ('ijkl,ji->kl','ijkl,jk->il'), aosym='s8')
            return Z2*(vj - vk)
        else:
            ddm = numpy.asarray(dm) - numpy.asarray(dm_last)
            vj, vk = scf.jk.get_jk(mol, (ddm, ddm), ('ijkl,ji->kl','ijkl,jk->il'), aosym='s8')
            return Z2*(vj - vk)  + numpy.asarray(vhf_last)

    def elec_nuc_coulomb(self, dm_elec, dm_nuc):
        'the energy of Coulomb interactions between electrons and quantum nuclei'
        mol = self.mol
        jcross = 0
        for i in range(len(dm_nuc)):
            jcross -= scf.jk.get_jk((mol.elec, mol.elec, mol.nuc[i], mol.nuc[i]), dm_nuc[i], scripts='ijkl,lk->ij', intor='int2e', aosym = 's4') * mol._atm[mol.nuc[i].atom_index, 0]
        if self.restrict == False:
            E = numpy.einsum('ij,ji', jcross, dm_elec[0] + dm_elec[1])
        else:
            E = numpy.einsum('ij,ji', jcross, dm_elec)
        logger.debug(self, 'Energy of e-n Coulomb interactions: %s', E)
        return E

    def nuc_nuc_coulomb(self, dm_nuc):
        'the energy of Coulomb interactions between quantum nuclei'
        mol = self.mol
        E = 0
        for i in range(len(dm_nuc)):
            for j in range(len(dm_nuc)):
                if j != i:
                    jcross = scf.jk.get_jk((mol.nuc[i], mol.nuc[i], mol.nuc[j], mol.nuc[j]), dm_nuc[j], scripts='ijkl,lk->ij', aosym='s4') * mol._atm[mol.nuc[i].atom_index, 0] * mol._atm[mol.nuc[j].atom_index, 0]
                    E += numpy.einsum('ij,ji', jcross, dm_nuc[i])

        logger.debug(self, 'Energy of n-n Comlomb interactions: %s', E*.5) # double counted
        return E*.5 

    def energy_tot(self, mf_elec, mf_nuc):
        'Total energy of NEO'
        mol = self.mol
        E_tot = 0

        self.dm_elec = mf_elec.make_rdm1()
        for i in range(len(mf_nuc)):
            self.dm_nuc[i] = mf_nuc[i].make_rdm1()

        h1e = mf_elec.get_hcore(mf_elec.mol)
        if self.restrict == False:
            e1 = numpy.einsum('ij,ji', h1e, self.dm_elec[0] + self.dm_elec[1])
        else:
            e1 = numpy.einsum('ij,ji', h1e, self.dm_elec)
        logger.debug(self, 'Energy of e1: %s', e1)

        vhf = mf_elec.get_veff(mf_elec.mol, self.dm_elec)
        if self.restrict == False:
            e_coul = (numpy.einsum('ij,ji', vhf[0], self.dm_elec[0]) +
                    numpy.einsum('ij,ji', vhf[1], self.dm_elec[1])) * .5 
        else:
            e_coul = numpy.einsum('ij,ji', vhf, self.dm_elec)
        logger.debug(self, 'Energy of e-e Coulomb interactions: %s', e_coul)

        E_tot += mf_elec.energy_elec(dm = self.dm_elec, h1e = h1e, vhf = vhf)[0] 

        for i in range(len(mf_nuc)):
            index = mf_nuc[i].mol.atom_index
            h1n = mf_nuc[i].get_hcore(mf_nuc[i].mol)
            n1 = numpy.einsum('ij,ji', h1n, self.dm_nuc[i])
            logger.debug(self, 'Energy of %s: %s', self.mol.atom_symbol(index), n1)
            E_tot += n1

        E_tot =  E_tot - self.elec_nuc_coulomb(self.dm_elec, self.dm_nuc) - self.nuc_nuc_coulomb(self.dm_nuc) + mf_elec.energy_nuc() # substract repeatedly counted terms

        return E_tot


    def scf(self, conv_tol = 1e-7, max_cycle = 60, dm0_elec = None, dm0_nuc = None):
        'self-consistent field driver for NEO'

        self.dm_elec = self.mf_elec.init_guess_by_atom()

        # set up the Hamiltonian for each quantum nucleus
        self.mf_nuc = [None] * self.mol.nuc_num
        for i in range(len(self.mol.nuc)):
            self.mf_nuc[i] = scf.RHF(self.mol.nuc[i])
            self.mf_nuc[i].get_init_guess = self.get_init_guess_nuc
            self.mf_nuc[i].get_hcore = self.get_hcore_nuc
            self.mf_nuc[i].get_veff = self.get_veff_nuc_bare
            self.mf_nuc[i].get_occ = self.get_occ_nuc
            self.dm_nuc[i] = self.get_init_guess_nuc(self.mol.nuc[i])

        self.mf_elec.scf(self.dm0_elec)
        self.dm_elec = self.mf_elec.make_rdm1()

        for i in range(len(self.mf_nuc)):
            self.mf_nuc[i].kernel(dump_chk=False)
            self.dm_nuc[i] = self.mf_nuc[i].make_rdm1()

        # update density matrix for electrons and quantum nuclei
        #self.dm_elec = self.mf_elec.make_rdm1()
        #for i in range(len(self.mf_nuc)):
        #    self.dm_nuc[i] = self.mf_nuc[i].make_rdm1()

        E_tot = self.energy_tot(self.mf_elec, self.mf_nuc)
        logger.info(self, 'Initial total Energy of NEO: %.15g\n' %(E_tot))

        scf_conv = False
        cycle = 0

        while not scf_conv:
            cycle += 1
            if cycle > max_cycle:
                raise RuntimeError('SCF is not convergent within %i cycles' %(max_cycle))

            E_last = E_tot
            self.mf_elec.scf(self.dm0_elec)
            self.dm_elec = self.mf_elec.make_rdm1()
            for i in range(len(self.mf_nuc)):
                self.mf_nuc[i].kernel(dump_chk=False)
                self.dm_nuc[i] = self.mf_nuc[i].make_rdm1()

            # update density matrix for electrons and quantum nuclei
            #self.dm_elec = self.mf_elec.make_rdm1()
            #for i in range(len(self.mf_nuc)):
            #    self.dm_nuc[i] = self.mf_nuc[i].make_rdm1()

            E_tot = self.energy_tot(self.mf_elec, self.mf_nuc)
            logger.info(self, 'Cycle %i Total Energy of NEO: %s\n' %(cycle, E_tot))
            if abs(E_tot - E_last) < conv_tol:
                scf_conv = True
                logger.debug(self, 'The eigenvalues of the electrons:\n%s', self.mf_elec.mo_energy)

                kinetic_energy = 0
                for i in range(len(self.mf_nuc)):
                    logger.debug(self, 'The eigenvalues of the quantum nucleus:\n%s', self.mf_nuc[i].mo_energy)
                    logger.debug(self, 'The coefficents of the quantum nucleus:\n%s', self.mf_nuc[i].mo_coeff)
                    k = numpy.einsum('ij,ji', self.mol.nuc[i].intor_symmetric('int1e_kin')/(1836.15267343 * self.mol.mass[self.mol.nuc[i].atom_index]), self.dm_nuc[i])
                    kinetic_energy += k
                    x = numpy.einsum('xij,ji->x', self.mol.nuc[i].intor_symmetric('int1e_r', comp=3), self.dm_nuc[i])
                    logger.debug(self, 'Expectational position %s' %(x))

                logger.debug(self, 'after substracting kinetic energy: %.15g', E_tot - k) 
                logger.note(self, 'converged NEO energy = %.15g', E_tot)
                return E_tot
