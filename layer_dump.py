'''
Modified version by yuw453
'''
import sys
import os
import numpy as np
import scipy.cluster.vq as scv
#_maohz
from jinja2 import Template

def kmeans(net, layers, num_c=16, initials=None, snapshot=False, alpha=0.0):            
    codebook = {}                                                                           
    if type(num_c) == type(1):                                                              
        num_c = [num_c] * len(layers)                                                       
    else:                                                                                   
        assert len(num_c) == len(layers)                                                    
                                                                                            
    print ("==============Perform K-means============="   )                                   
    for idx, layer in enumerate(layers):                                                    
        print ("Eval layer:", layer )                                                         
        W = net.params[layer][0].data.flatten()                                             
        W = W[np.where(W != 0)]                                                             
        if initials is None:  # Default: uniform sample                                     
            min_W = np.min(W)                                                               
            max_W = np.max(W)                                                               
            initial_uni = np.linspace(min_W, max_W, num_c[idx] - 1)                         
                                                                                            
            codebook[layer], _= scv.kmeans(W, initial_uni) 
                                                                                            
        elif type(initials) == type(np.array([])):                                          
            codebook[layer], _ = scv.kmeans(W, initials)                                    
        elif initials == 'random':                                                          
            codebook[layer], _ = scv.kmeans(W, num_c[idx]-1)                                
                                                                                            
        codebook[layer] = np.append(0, codebook[layer])                                   
        print ("codebook size:", len(codebook[layer])   )                                     

    return codebook

def quantize_net(net, codebook):
    layers = codebook.keys()
    print ("================Perform quantization==============")
    for layer in layers:
        print ("Quantize layer:", layer)
        W = net.params[layer][0].data
        codes, _ = scv.vq(W.flatten(), codebook[layer])
        W_q = np.reshape(codebook[layer][codes], W.shape)
        np.copyto(net.params[layer][0].data, W_q)


def get_codes(net, codebook):
    layers = codebook.keys()                                          
    codes_W = {}
    codes_b = {}
    print ("================Perform quantization=============="     )   
    for layer in layers:                                              
        print ("Quantize layer:", layer    )                            
        W = net.params[layer][0].data                                 
        b = net.params[layer][1].data   
        codes, _ = scv.vq(W.flatten(), codebook[layer])           
        codes = np.reshape(codes, W.shape)             
        codes_W[layer] = np.array(codes, dtype=np.uint32)
        W_q = np.reshape(codebook[layer][codes], W.shape)
        np.copyto(net.params[layer][0].data, W_q)

        codes, _ = scv.vq(b.flatten(), codebook[layer])           
        codes = np.reshape(codes, b.shape)             
        codes_b[layer] = np.array(codes, dtype=np.uint32)
        b_q = np.reshape(codebook[layer][codes], b.shape)
        np.copyto(net.params[layer][1].data, b_q)

    return codes_W, codes_b

def get_csc(codes_W, codes_b, bank_num=64, max_jump = 16):
    layers = codes_W.keys()
    ptr = [np.array([0], dtype = np.uint32)] * bank_num
    spm = [np.array([], dtype = np.uint32)] * bank_num
    ind= [np.array([], dtype = np.uint32)] * bank_num
    layer_shift = np.zeros(len(layers) + 1, dtype=np.uint32)

    has_bias = [False] * bank_num

    for layer_id, layer in enumerate(layers):
        weights = codes_W[layer]
        bias = codes_b[layer]

        for idx in range(bank_num):
            tmp = np.take(weights, range(idx, weights.shape[0], bank_num), axis=0)
            tmp_bias = np.take(bias, range(idx, bias.shape[0], bank_num), axis=0)
            # bank_weights[idx,:tmp.shape[0]] = tmp
            # tmp_id = np.where(tmp == 0)
            # x_id = tmp_id[0]
            # y_id = tmp_id[1]
            if not has_bias[idx]:
                ptr_tmp = np.zeros(((tmp.shape[1]-1)/bank_num+1)*bank_num+2, dtype = np.uint32) # take bias into consideration
                has_bias[idx] = True
            else:
                ptr_tmp = np.zeros(((tmp.shape[1])/bank_num+1)*bank_num+2, dtype = np.uint32) # take bias into consideration
            
            # weights    
            spm_tmp = np.zeros(weights.size, dtype = np.uint32) # large enough
            ind_tmp = np.ones(weights.size, dtype = np.uint32) * (max_jump-1)# large enough
            for col in range(tmp.shape[1]):
                loc = np.where(tmp[:,col] != 0)[0]
                if len(loc) > 0:
                    distance_loc = np.append(loc[0], np.diff(loc)-1)  #jump 1 encode to 0
                    zeros = distance_loc/max_jump
                    idx_vec = np.cumsum(zeros+1)-1  #add the element itself. first one need -1
                    ptr_tmp[col+1] = idx_vec[-1]+1 + ptr_tmp[col]             #ptr
                    spm_tmp[ptr_tmp[col] + idx_vec] = tmp[loc, col]           #code
                    ind_tmp[ptr_tmp[col] + idx_vec] = distance_loc % max_jump #index
                else:
                    ptr_tmp[col+1] = ptr_tmp[col]
            
            ptr_tmp[tmp.shape[1]:-1] = ptr_tmp[tmp.shape[1]]

            # bias
            loc = np.where(tmp_bias != 0)[0]
            if len(loc) > 0:
                distance_loc = np.append(loc[0], np.diff(loc)-1)
                zeros = distance_loc / max_jump
                idx_vec = np.cumsum(zeros+1)-1
                ptr_tmp[-1] = idx_vec[-1]+1 + ptr_tmp[-2]
                spm_tmp[ptr_tmp[-2] + idx_vec] = tmp_bias[loc]
                ind_tmp[ptr_tmp[-2] + idx_vec] = distance_loc % max_jump
            else:
                ptr_tmp[-1] = ptr_tmp[-2]

            ptr[idx] = np.append(ptr[idx], ptr_tmp[1:] + ptr[idx][-1])
            spm[idx] = np.append(spm[idx], spm_tmp[:ptr_tmp[-1]])
            ind[idx] = np.append(ind[idx], ind_tmp[:ptr_tmp[-1]])

            print (len(ptr[idx]))
        layer_shift[layer_id+1] = ptr[0].size - 1


    return ptr, spm, ind, layer_shift[:-1] #pointer to the start address for ptr of each layer

def get():
    os.system("current CAFFE_ROOT = $CAFFE_ROOT\n")
    caffe_root = os.environ["CAFFE_ROOT"]
    #caffe_root = "C:\Users\wy624\Downloads\caffe_MSVC14_Release_CPU_Py3.6"

    sys.path.insert(0, caffe_root + 'python')
    os.chdir(caffe_root)
    import caffe

    #caffe.set_mode_gpu()      
    #caffe.set_device(0) 
    
    caffe.set_mode_cpu()                                         
                                                   
    option = 'alexnet'

    if option == 'lenet5':                                             
        prototxt = '3_prototxt_solver/lenet5/train_val.prototxt'       
        caffemodel = '4_model_checkpoint/lenet5/lenet5.caffemodel'     
    elif option == 'alexnet':                                          
        prototxt = '3_prototxt_solver/L2/train_val.prototxt'           
        caffemodel = '4_model_checkpoint/alexnet/alexnet9x.caffemodel' 
    elif option == 'vgg':
        prototxt = '3_prototxt_solver/vgg16/train_val.prototxt'     
        caffemodel = '4_model_checkpoint/vgg16/vgg16_13x.caffemodel'

    #debug
    prototxt = 'models/bvlc_reference_caffenet/deploy.prototxt'
    caffemodel = 'models/bvlc_reference_caffenet/bvlc_reference_caffenet.caffemodel'

    net = caffe.Net(prototxt, caffemodel, caffe.TEST)
    if option == 'lenet5':
        layers = ['ip1']
        bank_num = 4
    else:
        layers = ['fc7']
        bank_num = 32

    codebook = kmeans(net, layers)
    codes_W, codes_b = get_codes(net, codebook)
    ptr, spm, ind, layer_shift= get_csc(codes_W, codes_b, bank_num = bank_num, max_jump = 16)

    #in linux: export SIMULATOR_PATH=/workspace
    #simulator_root = os.environ['SIMULATOR_PATH']
    
    #in debug
    simulator_root = '.'

    os.system("rm -rf %s/data/ptr"%simulator_root)
    os.system("rm -rf %s/data/spm"%simulator_root)
    os.system("mkdir %s/data/ptr"%simulator_root)
    os.system("mkdir %s/data/spm"%simulator_root)

    max_memsize = 0
    mem_a = [0] * bank_num
    for idx in range(bank_num):
        with open("%s/data/ptr/ptr%d.dat"%(simulator_root, idx), 'wb') as f:
            ptr[idx].tofile(f, sep=' ')

        with open("%s/data/spm/spm%d.dat"%(simulator_root, idx), 'wb') as f:
            mem = np.transpose(np.array([spm[idx],ind[idx]])).flatten()
            if (mem.size > max_memsize):
                max_memsize = mem.size
            mem.tofile(f, sep=' ')
            mem_a[idx] = mem

    with open("%s/data/arithm.dat"%simulator_root, 'wb') as f:
        for key in codebook:
            codebook_t = np.array(codebook[key], dtype=np.float32)
            codebook_t.tofile(f, sep=' ')
        
# Render config header file
    template = r'''
    // Auto generated by script/layer_dump.py

#ifndef PARAMS
#define PARAMS

    // Config harware
    const int NUM_PE = {{ bank_num }};
    const int ACTRW_maxcapacity = {{ max_size }};
    const int NZFETCH_buffersize = {{ buffer_size }};  
    const int PTRVEC_num_lines = {{ ptr_lines }};  
    const int SPMAT_unit_line   =  {{ spm_unitsize }};  // Nzeros per line
    const int SPMAT_num_lines   =  {{ spm_lines }}; 
    const int SPMAT_index_bits  =  4;  
    const int SPMAT_weights_bits=  4;  
    const int ARITHM_codebooksize = 16;

    // Config input data
    const int ACT_length = {{act_length}};
#endif
    '''
###################################################
# Configuration
    spm_unitsize = 16  # 16 code + 16 index
    buffer_size = 4

##################################################
    batch_size = net.blobs['data'].data.shape[0]
    import IPython
    IPython.embed()
    for i in range(1):
        net.forward()

    one_act = 1 # For debug

    if option == 'lenet5':
        if one_act:
            act = np.array([2.0, 0.0, 1.0], dtype=np.float32)
            ground_truth = 2.0 * net.params['ip1'][0].data[:,0] + 1.0 * net.params['ip1'][0].data[:,2]
        else:
            act = net.blobs['pool2'].data[idx % batch_size]
            ground_truth = net.blobs['ip1'].data[idx % batch_size]
    else:
        act = net.blobs['fc6'].data[0]
        ground_truth = net.blobs['fc7'].data[0]

    if option == "lenet5":
        max_inputsize = 1024
    else:
        max_inputsize = 4096
    act_length = act.size

    jtem = Template(template)
    config_file = jtem.render(bank_num = bank_num, ptr_lines = ptr[0].size, 
        spm_unitsize = spm_unitsize, spm_lines = (max_memsize - 1) / spm_unitsize / 2 + 1, 
        max_size = max_inputsize, act_length = act_length, buffer_size = buffer_size)

    with open("%s/data/act.dat"%simulator_root, 'wb') as f:
        act.tofile(f, sep=' ')

    with open("%s/data/groundtruth.dat"%simulator_root, 'wb') as f:
        ground_truth.tofile(f, sep=' ')
     
    with open("%s/src/params.h"%(simulator_root), 'w') as f:
        f.write(config_file)

if __name__ == "__main__":
    get()
