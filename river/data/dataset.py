import numpy as np
import torch
from torch.utils.data import Dataset, DataLoader
import torchvision.transforms as transforms
#from .utils import PARAMETER_NAMES_ALL_PRECESSINGBNS_BILBY
from .utils import * 
#from ..models.utils import project_strain_data_FDAPhi
import pickle
import random


def reparameterize_mass(mass):
    return np.log10(mass)

class DatasetStrainFD(Dataset):
    def __init__(self, data_dict, parameter_names):
        self.farray = torch.from_numpy(data_dict['farray']).float()
        self.Nsample = data_dict['Nsample'][0]
        self.paradim = len(parameter_names)
        self.detector_names = list(data_dict['strains'].keys())

        self.injection_parameters = np.zeros((self.Nsample, self.paradim))
        for i, parameter_name in enumerate(parameter_names):
            if parameter_name in ['chirp_mass']:
                self.injection_parameters[:,i] = reparameterize_mass(data_dict['injection_parameters'][parameter_name])
            else:
                self.injection_parameters[:,i] = data_dict['injection_parameters'][parameter_name]
        self.injection_parameters = torch.from_numpy(self.injection_parameters).float()

        s = np.array(list(data_dict['strains'][detname] for detname in self.detector_names ))
        psd = np.array(list(data_dict['PSDs'][detname] for detname in self.detector_names ))
        inv_asd = np.float32(1 / (psd**0.5))
        ###s_whitened = np.complex64(s*inv_asd)
        s_whitened = np.complex64(s*1e23)
        self.inv_asd = torch.from_numpy(inv_asd*1e-23).movedim(0,1).float()
        self.strain = torch.from_numpy(s_whitened).movedim(0,1) # is complex

        #strain_r = np.real(s_whitened)
        #strain_i = np.imag(s_whitened)
        #self.strain1 = torch.from_numpy(strain1).movedim(0,1).float()
        #self.strain2 = torch.from_numpy(strain2).movedim(0,1).float()


    def __len__(self):
        return self.Nsample

    def __getitem__(self, index):
        theta = self.injection_parameters[index]
        inv_asd = self.inv_asd[index]
        strain = self.strain[index]

        return theta, strain, inv_asd


class DatasetXFromPreCalSVDData(Dataset):
    '''
    From pre-calculated data, stored in SVD that can be feed into embedding layer directly
    '''
    def __init__(self, precaldata_list,  parameter_names):
        #self.farray = torch.from_numpy(data_dict['farray']).float()

        self.precaldata_list = precaldata_list
        self.sample_per_file = len(precaldata_list[0]['injection_parameters']['chirp_mass'])
        self.nfile = len(self.precaldata_list)
        self.Nsample = self.nfile * self.sample_per_file 

        self.parameter_names = parameter_names

    def __len__(self):
        return self.Nsample

    def __getitem__(self, index):
        index_precaldata_list, index_data_dict = self.get_data_index(index)
        x = torch.from_numpy( self.precaldata_list[index_precaldata_list]['x'][index_data_dict] ).float()
        theta = self.get_theta(self.precaldata_list[index_precaldata_list]['injection_parameters'], index_data_dict)

        return theta, x

    def get_data_index(self, index):
        index_precaldata_list = index // self.sample_per_file
        index_data_dict = index - index_precaldata_list*self.sample_per_file

        return index_precaldata_list, index_data_dict

    def get_theta(self, injection_parameters_all, index):
        theta = []
        for paraname in self.parameter_names:
            tt = injection_parameters_all[paraname][index]
            theta.append(tt)
            '''
            if paraname in ['chirp_mass']:
                theta.append(reparameterize_mass(tt))
            elif paraname in ['ra', 'dec', 'psi', 'phi', 'phi_12', 'phi_jl', 'tilt_1', 'tilt_2', 'theta_jn']:
                theta.append(tt/np.pi)
            elif paraname in ['luminosity_distance']:
                theta.append(tt/100)
            elif paraname in ['lambda_tilde', 'delta_lambda_tilde']:
                theta.append(tt/1000)
            else:
                theta.append(tt)
            '''
        return torch.from_numpy(np.array(theta)).float()



class DatasetXFromPreCalSVDData2D(Dataset):
    '''
    From pre-calculated data, stored in SVD that can be feed into embedding layer directly
    '''
    def __init__(self, precaldata_list,  parameter_names):
        #self.farray = torch.from_numpy(data_dict['farray']).float()

        self.precaldata_list = precaldata_list
        self.sample_per_file = len(precaldata_list[0]['injection_parameters']['chirp_mass'])
        self.nfile = len(self.precaldata_list)
        self.Nsample = self.nfile * self.sample_per_file 

        self.parameter_names = parameter_names

    def __len__(self):
        return self.Nsample

    def __getitem__(self, index):
        index_precaldata_list, index_data_dict = self.get_data_index(index)
        x = torch.from_numpy( self.precaldata_list[index_precaldata_list]['x'][index_data_dict] ).float()
        theta = self.get_theta(self.precaldata_list[index_precaldata_list]['injection_parameters'], index_data_dict)

        return theta, x

    def get_data_index(self, index):
        index_precaldata_list = index // self.sample_per_file
        index_data_dict = index - index_precaldata_list*self.sample_per_file

        return index_precaldata_list, index_data_dict

    def get_theta(self, injection_parameters_all, index):
        theta = []
        for paraname in self.parameter_names:
            if paraname in ['chirp_mass', 'mass_ratio']:
                tt = injection_parameters_all[paraname][index]
                theta.append(tt)
            '''
            if paraname in ['chirp_mass']:
                theta.append(reparameterize_mass(tt))
            elif paraname in ['ra', 'dec', 'psi', 'phi', 'phi_12', 'phi_jl', 'tilt_1', 'tilt_2', 'theta_jn']:
                theta.append(tt/np.pi)
            elif paraname in ['luminosity_distance']:
                theta.append(tt/100)
            elif paraname in ['lambda_tilde', 'delta_lambda_tilde']:
                theta.append(tt/1000)
            else:
                theta.append(tt)
            '''
        return torch.from_numpy(np.array(theta)).float()
    

class DatasetSVDStrainFDFromSVDWF(Dataset):
    '''
    Simulate FD data in SVD space from pre-calculated SVD waveforms. 
    '''
    def __init__(self, precalwf_list,  parameter_names, data_generator, Nbasis, V, dmin=10, dmax=200, dpower=1):
        #self.farray = torch.from_numpy(data_dict['farray']).float()

        self.precalwf_list = precalwf_list
        self.sample_per_file = len(precalwf_list[0]['injection_parameters']['chirp_mass'])
        self.nfile = len(self.precalwf_list)
        self.Nsample = self.nfile * self.sample_per_file 

        self.dmin = dmin
        self.dmax = dmax
        self.dpower = dpower
        
        self.parameter_names = parameter_names
        self.paradim = len(parameter_names)
        self.data_generator = data_generator
        self.detector_names = data_generator.detector_names
        #self.ipca_gen = ipca_gen
        self.V = V
        self.Vh = V.T.conj()
        self.Nbasis = Nbasis

    def __len__(self):
        return self.Nsample

    def __getitem__(self, index):
        index_precalwf_list, index_wf_dict = self.get_wf_index(index)
        
        wf_dict = load_dict_from_hdf5(pp)

        hp_svd = wf_dict['waveform_polarizations']['plus']['amplitude'][testid] * np.exp(1j*wf_dict['waveform_polarizations']['plus']['phase'][testid])

        
        #wf_dict = self.data_generator.get_one_waveform(index_wf_dict, self.precalwf_list[index_precalwf_list]['waveform_polarizations'])
        injection_parameters = self.data_generator.get_one_injection_parameters(index_wf_dict,  self.precalwf_list[index_precalwf_list]['injection_parameters'], is_intrinsic_only=True)
        injection_parameters = self.update_injection_parameters(injection_parameters)

        #while not self.data_generator.inject_one_signal_from_waveforms(injection_parameters, wf_dict):
        #    injection_parameters = self.update_injection_parameters(injection_parameters) # until this injection can be detected
        
        data_dict = self.data_generator.data
        s = np.array(list(data_dict['strains'][detname] for detname in self.detector_names ))
        psd = np.array(list(data_dict['PSDs'][detname] for detname in self.detector_names ))
        inv_asd = np.float32(1 / (psd**0.5))
        ###s_whitened = np.complex64(s*inv_asd)
        s_whitened = np.complex64(s*1e23)

        inv_asd = torch.from_numpy(inv_asd*1e-23).movedim(0,1).float()[0]
        strain = torch.from_numpy(s_whitened).movedim(0,1)[0] # is complex
        theta = self.get_theta(injection_parameters)

        x = self._project_strain_data_FDAPhi(strain, inv_asd, self.detector_names, self.ipca_gen)
        self.data_generator.initialize_data()
        #return theta.clone().detach(), strain.clone().detach(), inv_asd.clone().detach()
        return theta.clone().detach(), x.squeeze(0).clone().detach()

    def get_wf_index(self, index):
        index_precalwf_list = index // self.sample_per_file
        index_wf_dict = index - index_precalwf_list*self.sample_per_file

        return index_precalwf_list, index_wf_dict

    def update_injection_parameters(self, injection_parameters):
        injection_parameters['ra'] = np.random.uniform(0, np.pi)
        injection_parameters['dec'] = np.arcsin(np.random.uniform(-1, 1))
        injection_parameters['psi'] = np.random.uniform(0, np.pi)
        injection_parameters['geocent_time'] = np.random.uniform(-0.1, 0.1)
        injection_parameters['luminosity_distance'] = generate_random_distance(Nsample=1, low=self.dmin, high=self.dmax, power=self.dpower)[0]

        return injection_parameters
   
    def get_theta(self, injection_parameters):
        theta = []
        for paraname in self.parameter_names:
            tt = injection_parameters[paraname]
            if paraname in ['chirp_mass']:
                theta.append(reparameterize_mass(tt))
            else:
                theta.append(tt)
        
        return torch.from_numpy(np.array(theta)).float()

    def _project_strain_data_FDAPhi(self, strain, psd, detector_names, ipca_gen, project=True, downsample_rate=1, dim=1):
        '''
        strain: DatasetStrainFD in batches, e.g. DatasetStrainFD[0:10]
        psd: strain-like
        detector_names: DatasetStrainFD.detector_names
        ipca_gen: IPCAGenerator
        '''
        strain = np.expand_dims(strain, 0)
        psd = np.expand_dims(psd, 0)
        strain_amp = np.abs(strain)
        strain_phi = np.unwrap(np.angle(strain) , axis=-1)
        strain_real = np.real(strain)
        strain_imag = np.imag(strain)

        n_components = ipca_gen.n_components
        batch_size = strain.shape[0]
        ndet = len(detector_names)

        output_amp = []
        output_phi = []
        output_psd = []
        for i,detname in enumerate(detector_names):
            if project:
                output_amp.append(ipca_gen.project(strain_amp[:,i,:], detname, 'amplitude'))
                output_phi.append(ipca_gen.project(strain_phi[:,i,:], detname, 'phase'))
                output_psd.append(ipca_gen.project(psd[:,i,:], detname, 'amplitude'))
            else:
                output_amp.append(strain_amp.numpy()[:,i,:][:,::downsample_rate])
                output_phi.append(strain_phi[:,i,:][:,::downsample_rate])
                #output_amp.append(strain_real.numpy()[:,i,:][:,::downsample_rate])
                #output_phi.append(strain_imag.numpy()[:,i,:][:,::downsample_rate])
                output_psd.append(psd.numpy()[:,i,:][:,::downsample_rate])

        output_amp = torch.from_numpy(np.array(output_amp))
        output_phi = torch.from_numpy(np.array(output_phi))
        output_psd = torch.from_numpy(np.array(output_psd))
        data_length = output_amp.shape[-1]
        if dim==1:
            return torch.cat((output_amp, output_phi, output_psd)).movedim(0,1).float()
        elif dim==2:
            return torch.cat((output_amp, output_phi, output_psd)).movedim(0,1).float().view((batch_size,3,ndet,data_length))

class DatasetStrainFDFromFolder(Dataset):
    def __init__(self, data_folder, filename_prefix,  parameter_names, ipca, data_generator, nbatch = 100, file_per_batch = 1000, sample_per_file = 10):
        #self.farray = torch.from_numpy(data_dict['farray']).float()

        self.data_folder = data_folder
        self.filename_prefix = filename_prefix
        self.nbatch = nbatch
        self.file_per_batch = file_per_batch
        self.sample_per_file = sample_per_file
        self.Nsample = self.nbatch * self.file_per_batch * self.sample_per_file
        self.paradim = len(parameter_names)
        self.data_generator = data_generator


        self.detector_names = list(data_dict['strains'].keys())

        self.injection_parameters = np.zeros((self.Nsample, self.paradim))
        for i, parameter_name in enumerate(parameter_names):
            if parameter_name in ['chirp_mass']:
                self.injection_parameters[:,i] = reparameterize_mass(data_dict['injection_parameters'][parameter_name])
            else:
                self.injection_parameters[:,i] = data_dict['injection_parameters'][parameter_name]
        self.injection_parameters = torch.from_numpy(self.injection_parameters).float()

        s = np.array(list(data_dict['strains'][detname] for detname in self.detector_names ))
        psd = np.array(list(data_dict['PSDs'][detname] for detname in self.detector_names ))
        inv_asd = np.float32(1 / (psd**0.5))
        ###s_whitened = np.complex64(s*inv_asd)
        s_whitened = np.complex64(s*1e23)
        self.inv_asd = torch.from_numpy(inv_asd*1e-23).movedim(0,1).float()
        self.strain = torch.from_numpy(s_whitened).movedim(0,1) # is complex

        #strain_r = np.real(s_whitened)
        #strain_i = np.imag(s_whitened)
        #self.strain1 = torch.from_numpy(strain1).movedim(0,1).float()
        #self.strain2 = torch.from_numpy(strain2).movedim(0,1).float()

    def __len__(self):
        return self.Nsample

    def __getitem__(self, index):
        filepath, index_inside_file = self.get_file_path_and_index(index)
        file_dict = load_dict_from_hdf5(filepath)
        wf_dict = file_dict['waveform_polarizations'][index_inside_file]


        self.data_generator.inject_one_signal_from_waveforms(injection_parameters_dict, wf_dict)


        theta = self.injection_parameters[index]
        inv_asd = self.inv_asd[index]
        strain = self.strain[index]

        return theta, strain, inv_asd

    def get_file_path_and_index(self, index):
        sample_per_batch = self.sample_per_file * self.file_per_batch
        batch_number = index // sample_per_batch
        file_number = (index - sample_per_batch*batch_number) // self.file_per_batch
        index_inside_file = int( index - sample_per_batch*batch_number - self.sample_per_file*file_number )

        return f"{self.data_folder}/batch{batch_number}/{self.filename_prefix}{index_inside_file}.h5", index_inside_file



def loadVandVh(Vhfilepath, Nbasis):
    with open(Vhfilepath, 'rb') as f:
        Vh = pickle.load(f)
    if len(Vh)<Nbasis:
        raise ValueError(f'required Nbasis ({Nbasis}) > len(Vh) ({len(Vh)})!')
    Vh = Vh[:Nbasis]
    V = Vh.T.conj()
        
    return V, Vh


class DatasetSVDStrainFDFromSVDWFonGPU(Dataset):
    '''
    Simulate FD data in SVD space from pre-calculated SVD waveforms, optimized for GPU or CPU computation.
    '''
    def __init__(self, precalwf_filelist, parameter_names, data_generator, Nbasis, Vhfile,
                dmin=10, dmax=200, dpower=1, loadwf=False, loadnoise=False, device='cuda',
                complex = False, add_noise=True, fix_extrinsic=False, shuffle=True):
        self.precalwf_filelist = precalwf_filelist
        self.parameter_names = parameter_names
        self.data_generator = data_generator
        self.Nbasis = Nbasis
        self.dmin = dmin
        self.dmax = dmax
        self.dpower = dpower
        self.loadwf = loadwf
        self.loadnoise = loadnoise
        self.device = device
        self.complex = complex
        self.add_noise = add_noise
        self.fix_extrinsic = fix_extrinsic
        self.shuffle = shuffle

        # Load V and Vh matrices and convert to tensors
        self.V, self.Vh = loadVandVh(Vhfile, Nbasis)
        self.V = torch.from_numpy(self.V).to(self.device).type(torch.complex64)
        self.Vh = torch.from_numpy(self.Vh).to(self.device).type(torch.complex64)

        
        self.farray = torch.from_numpy(data_generator.frequency_array_masked).float().to(self.device)
        self.ifos = data_generator.ifos
        self.det_data = self.prepare_detector_data()
        
        testfile = load_dict_from_hdf5(precalwf_filelist[0])
        self.sample_per_file = len(testfile['injection_parameters']['chirp_mass'])
        self.Nfile = len(self.precalwf_filelist)
        self.Nsample = self.Nfile * self.sample_per_file 
        self.cached_wf_file = testfile
        self.cached_wf_file_index = 0
        
        self.shuffle_indexinfile()
            
    def prepare_detector_data(self):
        det_data = {}
        for det in self.ifos:
            detname = det.name
            psd = det.power_spectral_density_array[self.data_generator.frequency_mask]
            psd = torch.from_numpy(psd).double().to(self.device)
            whitened_V = (self.V.T * 1/(psd*det.duration/4)**0.5).T
            det_data[detname] = {'whitened_V': whitened_V.type(torch.complex64)}
        return det_data

    def __len__(self):
        return len(self.precalwf_filelist) * self.sample_per_file

    def __getitem__(self, index):
        index_of_file, index_in_file = self.get_index(index, self.sample_per_file)
        wf_dict = self.get_precalwf_dict(index_of_file)
        hp_svd, hc_svd = self.get_waveform_tensors(wf_dict, index_in_file)

        injection_parameters = self.get_injection_parameters(wf_dict,index_in_file)
        injection_parameters = self.update_injection_parameters(injection_parameters)
        hp_svd = hp_svd/injection_parameters['luminosity_distance']
        hc_svd = hc_svd/injection_parameters['luminosity_distance']
        #x_real, x_imag = self.compute_strain_tensors(hp_svd, hc_svd, injection_parameters)
        x = self.compute_strain_tensors(hp_svd, hc_svd, injection_parameters)

        theta = self.get_theta(injection_parameters)
        if self.complex:
            return theta, x 
        else:
            return theta, torch.cat((x.real, x.imag)).float()

    def get_index(self, index, sample_per_file):
        index_of_file = index // sample_per_file
        index_in_file = index - index_of_file*sample_per_file
        
        return index_of_file, index_in_file
    
    def get_precalwf_dict(self, index_of_file):
        if self.cached_wf_file_index == index_of_file:
            return self.cached_wf_file
        else:
            wf_dict = load_dict_from_hdf5(self.precalwf_filelist[index_of_file])
            self.cached_wf_file = wf_dict
            self.cached_wf_file_index = index_of_file
            return wf_dict
        
    def get_waveform_tensors(self, wf_dict, index_in_file):
        index_in_file = self.random_index_in_file[index_in_file]
        hp_svd = (torch.from_numpy(wf_dict['waveform_polarizations']['plus']['amplitude'][index_in_file]) *\
            torch.exp(1j*torch.from_numpy(wf_dict['waveform_polarizations']['plus']['phase'][index_in_file])).type(torch.complex64)).to(self.device)
        hc_svd = (torch.from_numpy(wf_dict['waveform_polarizations']['cross']['amplitude'][index_in_file]) *\
            torch.exp(1j*torch.from_numpy(wf_dict['waveform_polarizations']['cross']['phase'][index_in_file])).type(torch.complex64)).to(self.device)
        
        return hp_svd, hc_svd

    def get_injection_parameters(self, wf_dict, index_in_file):
        index_in_file = self.random_index_in_file[index_in_file]
        injection_parameters = {key: wf_dict['injection_parameters'][key][index_in_file] for key in ['chirp_mass', 'mass_ratio', 'a_1', 'a_2', 'tilt_1', 'tilt_2', 'phi_12', 'phi_jl',
                    'lambda_tilde', 'delta_lambda_tilde', 'theta_jn', 'phase']}
        return injection_parameters

    def get_noise_tensors(self, ):
        white_noise = (torch.randn(self.Nbasis, device=self.device) + 1j * torch.randn(self.Nbasis, device=self.device)).type(torch.complex64)

        return white_noise
    
    def compute_strain_tensors(self, hp_svd, hc_svd, injection_parameters):
        num_ifos = len(self.ifos)
        #x_real = torch.zeros((num_ifos, self.Nbasis), dtype=torch.float32, device=self.device)
        #x_imag = torch.zeros((num_ifos, self.Nbasis), dtype=torch.float32, device=self.device)
        x = torch.zeros((num_ifos, self.Nbasis), dtype=torch.complex64, device=self.device)
        for i, det in enumerate(self.ifos):
            detname = det.name

            fp, fc, dt = self.compute_detector_factors(det, injection_parameters)
            phase2add = torch.exp(-1j * 2 * np.pi * dt * self.farray)
            Vh_recons = self.Vh * phase2add.unsqueeze(0)  # Ensure proper broadcasting
            
            h_svd = torch.matmul(torch.matmul((fp*hp_svd + fc*hc_svd).type(torch.complex64), Vh_recons),
                                 self.det_data[detname]['whitened_V'])

            if self.add_noise:
                n_svd = self.get_noise_tensors()
                d_svd = h_svd + n_svd
            else:
                d_svd = h_svd
            
            #x_real[i] = d_svd.real
            #x_imag[i] = d_svd.imag
            x[i] = d_svd
        #return x_real, x_imag
        return x

    def compute_detector_factors(self, det, injection_parameters):
        # These calculations remain on CPU as they cannot be efficiently vectorized or moved to GPU
        ra = injection_parameters['ra']
        dec = injection_parameters['dec']
        tc = injection_parameters['geocent_time']
        psi = injection_parameters['psi']
        fp = det.antenna_response(ra , dec, tc, psi, 'plus')
        fc = det.antenna_response(ra , dec, tc, psi, 'cross')
        time_shift = det.time_delay_from_geocenter(ra , dec, tc)
        
        dt_geocent = tc #- self.strain_data.start_time
        dt = dt_geocent + time_shift
            
        return fp, fc, dt

    def get_theta(self, injection_parameters):
        theta = torch.tensor(np.array([injection_parameters[paraname] for paraname in self.parameter_names]), dtype=torch.float32).to(self.device)
        return theta
    
    def update_injection_parameters(self, injection_parameters):
        if self.fix_extrinsic:
            injection_parameters['ra'] = 1
            injection_parameters['dec'] = 1
            injection_parameters['psi'] = 1
            injection_parameters['geocent_time'] = 0
            #injection_parameters['luminosity_distance'] = generate_random_distance(Nsample=1, low=self.dmin, high=self.dmax, power=self.dpower)[0]
            injection_parameters['luminosity_distance'] = 100
        else:
            injection_parameters['ra'] = np.random.uniform(0, np.pi)
            injection_parameters['dec'] = np.arcsin(np.random.uniform(-1, 1))
            injection_parameters['psi'] = np.random.uniform(0, np.pi)
            injection_parameters['geocent_time'] = np.random.uniform(-0.1, 0.1)
            injection_parameters['luminosity_distance'] = generate_random_distance(Nsample=1, low=self.dmin, high=self.dmax, power=self.dpower)[0]
    
        return injection_parameters
    
    def shuffle_wflist(self):
        if self.shuffle:
            random.shuffle(self.precalwf_filelist)
        
    def shuffle_indexinfile(self):
        if self.shuffle:
            self.random_index_in_file = np.random.permutation(self.sample_per_file)
        else:
            self.random_index_in_file = np.arange(self.sample_per_file)

class DatasetSVDStrainFDFromSVDWFonGPUBatch(Dataset):
    '''
    Simulate FD data in SVD space from pre-calculated SVD waveforms, optimized for GPU or CPU computation.

    Load a batch of data, i.e. return [minibatch_size, dim1, dim2, ...]. The batch size should be 2^N. 
    '''
    def __init__(self, precalwf_filelist, parameter_names, data_generator, Nbasis, Vhfile,
                dmin=10, dmax=200, dpower=1, loadwf=False, loadnoise=False, device='cuda',
                complex=False, add_noise=True, minibatch_size=1, fix_extrinsic=False, shuffle=True):
        self.precalwf_filelist = precalwf_filelist
        self.parameter_names = parameter_names
        self.data_generator = data_generator
        self.Nbasis = Nbasis
        self.dmin = dmin
        self.dmax = dmax
        self.dpower = dpower
        self.loadwf = loadwf
        self.loadnoise = loadnoise
        self.device = device
        self.minibatch_size = minibatch_size
        self.complex = complex
        self.add_noise = add_noise
        self.fix_extrinsic = fix_extrinsic
        self.shuffle = shuffle

        # Load V and Vh matrices and convert to tensors
        self.V, self.Vh = loadVandVh(Vhfile, Nbasis)
        self.V = torch.from_numpy(self.V).to(self.device).type(torch.complex64)
        self.Vh = torch.from_numpy(self.Vh).to(self.device).type(torch.complex64)

        
        self.farray = torch.from_numpy(data_generator.frequency_array_masked).float().to(self.device)
        self.ifos = data_generator.ifos
        self.det_data = self.prepare_detector_data()
        
        testfile = load_dict_from_hdf5(precalwf_filelist[0])
        self.sample_per_file = len(testfile['injection_parameters']['chirp_mass'])
        #if self.sample_per_file<self.minibatch_size:
        #    raise ValueError("Sample per file < batch size!")
        self.Nfile = len(self.precalwf_filelist)
        self.Nsample = self.Nfile * self.sample_per_file 
        self.cached_wf_file = testfile
        self.cached_wf_file_index = 0
            
        self.shuffle_indexinfile()
        
    def prepare_detector_data(self):
        det_data = {}
        for det in self.ifos:
            detname = det.name
            psd = det.power_spectral_density_array[self.data_generator.frequency_mask]
            psd = torch.from_numpy(psd).double().to(self.device)
            whitened_V = (self.V.T * 1/(psd*det.duration/4)**0.5).T
            det_data[detname] = {'whitened_V': whitened_V.type(torch.complex64)}
        return det_data

    def __len__(self):
        return len(self.precalwf_filelist) * self.sample_per_file // self.minibatch_size

    def __getitem__(self, index):
        index = index*self.minibatch_size
        
        index_end = index + self.minibatch_size
        index_of_file, index_in_file = self.get_index(index, self.sample_per_file)
        index_of_file_end, index_in_file_end = self.get_index(index_end, self.sample_per_file)
        if index_of_file_end>=len(self.precalwf_filelist):
            index_of_file_end = len(self.precalwf_filelist)-1
            index_in_file_end = self.sample_per_file
        wf_dict_list = []
        for i in range(index_of_file, index_of_file_end+1):
            wf_dict_list.append(self.get_precalwf_dict(i))
        
        hp_svd, hc_svd = self.get_waveform_tensors_batch(wf_dict_list, index_in_file, index_in_file_end)
        injection_parameters = self.get_injection_parameters_batch(wf_dict_list,index_in_file, index_in_file_end)
        injection_parameters = self.update_injection_parameters_batch(injection_parameters)
        
        dL = torch.from_numpy(injection_parameters['luminosity_distance']).to(self.device).unsqueeze(-1)
        hp_svd = hp_svd/dL
        hc_svd = hc_svd/dL

        #x_real, x_imag = self.compute_strain_tensors_batch(hp_svd, hc_svd, injection_parameters)
        x = self.compute_strain_tensors_batch(hp_svd, hc_svd, injection_parameters)

        theta = self.get_theta(injection_parameters)
        if self.complex:
            return theta, x 
        else:
            return theta, torch.cat((x.real, x.imag), axis=1).float()

    def get_index(self, index, sample_per_file):
        index_of_file = index // sample_per_file
        index_in_file = index - index_of_file*sample_per_file

        return index_of_file, index_in_file
    
    def get_precalwf_dict(self, index_of_file):
        if self.cached_wf_file_index == index_of_file:
            return self.cached_wf_file
        else:
            try:
                wf_dict = load_dict_from_hdf5(self.precalwf_filelist[index_of_file])
            except:
                raise Exception(f'index_of_file: {index_of_file}')
            self.cached_wf_file = wf_dict
            self.cached_wf_file_index = index_of_file
            return wf_dict
        
    def get_waveform_tensors_batch(self, wf_dict_list, index_in_file, index_in_file_end):
        for i, wf_dict in enumerate(wf_dict_list):
            if i==len(wf_dict_list)-1:
                end_index = index_in_file_end
            else:
                end_index = self.sample_per_file
            if i==0:
                index = self.random_index_in_file[index_in_file:end_index]
                hp_svd = (torch.from_numpy(wf_dict['waveform_polarizations']['plus']['amplitude'][index]) *\
                    torch.exp(1j*torch.from_numpy(wf_dict['waveform_polarizations']['plus']['phase'][index])).type(torch.complex64)).to(self.device)
                hc_svd = (torch.from_numpy(wf_dict['waveform_polarizations']['cross']['amplitude'][index]) *\
                    torch.exp(1j*torch.from_numpy(wf_dict['waveform_polarizations']['cross']['phase'][index])).type(torch.complex64)).to(self.device)
            else:
                index = self.random_index_in_file[index_in_file:end_index]
                hp_svd_new = (torch.from_numpy(wf_dict['waveform_polarizations']['plus']['amplitude'][index]) *\
                    torch.exp(1j*torch.from_numpy(wf_dict['waveform_polarizations']['plus']['phase'][index])).type(torch.complex64)).to(self.device)
                hc_svd_new = (torch.from_numpy(wf_dict['waveform_polarizations']['cross']['amplitude'][index]) *\
                    torch.exp(1j*torch.from_numpy(wf_dict['waveform_polarizations']['cross']['phase'][index])).type(torch.complex64)).to(self.device)

                hp_svd = torch.cat((hp_svd,hp_svd_new))
                hc_svd = torch.cat((hc_svd,hc_svd_new))
                    
            
        return hp_svd, hc_svd

    def get_injection_parameters_batch(self, wf_dict_list, index_in_file, index_in_file_end):
        para_name_list = ['chirp_mass', 'mass_ratio', 'a_1', 'a_2', 'tilt_1', 'tilt_2', 'phi_12', 'phi_jl',
                    'lambda_tilde', 'delta_lambda_tilde', 'theta_jn', 'phase']
        for i, wf_dict in enumerate(wf_dict_list):
            if i==len(wf_dict_list)-1:
                end_index = index_in_file_end
            else:
                end_index = self.sample_per_file

            index_random = self.random_index_in_file[index_in_file:end_index]
            if i==0:
                injection_parameters = {key: wf_dict['injection_parameters'][key][index_random] for key in para_name_list}
            else:
                injection_parameters = {key: np.append(injection_parameters[key], wf_dict['injection_parameters'][key][index_random]) for key in para_name_list}

        return injection_parameters

    def get_noise_tensors_batch(self, ):
        white_noise = (torch.randn((self.minibatch_size, self.Nbasis), device=self.device) + \
                       1j * torch.randn((self.minibatch_size, self.Nbasis), device=self.device)).type(torch.complex64)

        return white_noise
    
    def compute_strain_tensors_batch(self, hp_svd, hc_svd, injection_parameters):
        num_ifos = len(self.ifos)
        #x_real = torch.zeros((self.minibatch_size, num_ifos, self.Nbasis), dtype=torch.float32, device=self.device)
        #x_imag = torch.zeros((self.minibatch_size, num_ifos, self.Nbasis), dtype=torch.float32, device=self.device)
        x = torch.zeros((self.minibatch_size, num_ifos, self.Nbasis), dtype=torch.complex64, device=self.device)
        for i,det in enumerate(self.ifos):
            detname = det.name
        
            fp, fc, dt = self.compute_detector_factors_batch(det, injection_parameters)
            phase2add = torch.exp(-1j * 2 * np.pi * dt * self.farray)
            Vh_recons = (self.Vh * phase2add.unsqueeze(0)).type(torch.complex64)  # Ensure proper broadcasting            
            hh = (fp*hp_svd + fc*hc_svd).type(torch.complex64)

            #h_svd = torch.matmul(torch.bmm(hh.unsqueeze(1), Vh_recons).squeeze(1),
            #                     self.det_data[detname]['whitened_V'])
            h_svd = torch.matmul(torch.matmul(hh, Vh_recons),
                                 self.det_data[detname]['whitened_V'])
            
            
            if self.add_noise:
                n_svd = self.get_noise_tensors_batch()
                d_svd = h_svd + n_svd
            else:
                d_svd = h_svd
            
            #x_real[:,i,:] = d_svd.real
            #x_imag[:,i,:] = d_svd.imag
            x[:,i,:] = d_svd
            

        return x
    
    def compute_detector_factors_batch(self, det, injection_parameters):
        # These calculations remain on CPU as they cannot be efficiently vectorized or moved to GPU
        #fp_tensor = torch.zeros((self.minibatch_size), dtype=torch.float32, device=self.device)
        #fc_tensor = torch.zeros((self.minibatch_size), dtype=torch.float32, device=self.device)
        #dt_tensor = torch.zeros((self.minibatch_size), dtype=torch.float32, device=self.device)
        '''
        for i in range(len(injection_parameters['ra'])):
            
            ra = injection_parameters['ra'][i]
            dec = injection_parameters['dec'][i]
            tc = injection_parameters['geocent_time'][i]
            psi = injection_parameters['psi'][i]
            
            fp = det.antenna_response(ra, dec, tc, psi, 'plus')
            fc = det.antenna_response(ra, dec, tc, psi, 'cross')
            time_shift = det.time_delay_from_geocenter(ra, dec, tc)
            
            dt_geocent = tc #- self.strain_data.start_time
            dt = dt_geocent + time_shift
            
            fp_tensor[i] = fp
            fc_tensor[i] = fc
            dt_tensor[i] = dt
        '''
        ra = injection_parameters['ra'][0]
        dec = injection_parameters['dec'][0]
        tc = injection_parameters['geocent_time'][0]
        psi = injection_parameters['psi'][0]

        fp = det.antenna_response(ra, dec, tc, psi, 'plus')
        fc = det.antenna_response(ra, dec, tc, psi, 'cross')
        time_shift = det.time_delay_from_geocenter(ra, dec, tc)

        dt_geocent = tc #- self.strain_data.start_time
        dt = dt_geocent + time_shift
        
        #return fp_tensor.unsqueeze(-1), fc_tensor.unsqueeze(-1), dt_tensor.unsqueeze(-1)
        return fp, fc, dt
    
    def get_theta(self, injection_parameters):
        theta = torch.tensor(np.array([injection_parameters[paraname] for paraname in self.parameter_names]), dtype=torch.float32).to(self.device).T
        return theta
    
    def update_injection_parameters_batch(self, injection_parameters):
        if self.fix_extrinsic:
            injection_parameters['ra'] = np.zeros(self.minibatch_size) + 1
            injection_parameters['dec'] = np.zeros(self.minibatch_size) + 1
            injection_parameters['psi'] = np.zeros(self.minibatch_size) + 1
            injection_parameters['geocent_time'] = np.zeros(self.minibatch_size) + 0
            #injection_parameters['luminosity_distance'] = generate_random_distance(Nsample=self.minibatch_size, low=self.dmin, high=self.dmax, power=self.dpower)
            injection_parameters['luminosity_distance'] = np.zeros(self.minibatch_size) + 100
    
        else:
            injection_parameters['ra'] = np.zeros(self.minibatch_size) + np.random.uniform(0, np.pi)
            injection_parameters['dec'] = np.zeros(self.minibatch_size) + np.arcsin(np.random.uniform(-1, 1))
            injection_parameters['psi'] = np.zeros(self.minibatch_size) + np.random.uniform(0, np.pi)
            injection_parameters['geocent_time'] = np.zeros(self.minibatch_size) + np.random.uniform(-0.1, 0.1)
            injection_parameters['luminosity_distance'] = generate_random_distance(Nsample=self.minibatch_size, low=self.dmin, high=self.dmax, power=self.dpower)
        
        return injection_parameters
    
    def shuffle_wflist(self):
        if self.shuffle:
            random.shuffle(self.precalwf_filelist)
        
    def shuffle_indexinfile(self):
        if self.shuffle:
            self.random_index_in_file = np.random.permutation(self.sample_per_file)
        else:
            self.random_index_in_file = np.arange(self.sample_per_file)



