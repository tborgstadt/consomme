import numpy as np
import matplotlib.pyplot as pl

from empca import *
from rotate_factor import varimax

class Bubble(object):
    """
    Factor Analysis deconvolution, using online learning.
    """
    def __init__(self,data,obsvar,latent_dim,
                 max_iter=100000,check_factor=1,
                 Nosc=5):
        """

        """
        assert data.shape==obsvar.shape, 'Data and obs. ' + \
            'variance have different shapes'
        if check_factor<1: 
            print 'Warning: checking for convergence ' + \
                'before seeing all the data.'

        self.N = data.shape[0]
        self.D = data.shape[1]
        self.M = latent_dim
        self.jitter = np.zeros(self.D) 

        # constant learning rates... fix soon.
        self.mean_rate = 1.e-8 # ok for now...
        self.jitter_rate = 1.e-8 # slams to zero
        self.lambda_rate = 1.e-3 # no clue

        # Suffling the data
        ind = np.random.permutation(self.N)
        self.data = data[ind,:]
        self.obsvar = obsvar[ind,:]

        self.initialize()
        self.initial_mean   = self.mean.copy()
        self.initial_jitter = self.jitter.copy()
        self.initial_lambda = self.lam.copy()
        self.initial_nll    = self.total_negative_log_likelihood()
        self.run_inference(max_iter,check_factor,Nosc)

    def initialize(self):

        # inverse variance weighted mean
        if np.sum(self.obsvar)!=0.0:
            self.mean = np.sum(self.data / self.obsvar,axis=0) / \
                np.sum(1.0 / self.obsvar,axis=0)
        else:
            self.mean = np.mean(self.data,axis=0)

        # use EM PCA to initialize factor loadings
        if self.M==0:
            self.lam = np.zeros(1)
        else:
            empca = EMPCA(self.data.T,self.M)
            R = varimax(empca.lam)
            self.lam = np.dot(empca.lam,R)
            
    def invert_cov(self):
        """
        Make inverse covariance, using the inversion lemma.
        """
        if self.M==0:
            self.inv_cov = np.diag(1.0 / (self.jitter + self.variance))
        else:
            # repeated in lemma
            lam = self.lam
            lamT = lam.T
            if np.sum(self.jitter+self.variance)!=0.0:
                psiI = np.diag(1.0 / (self.jitter + self.variance))
                psiIlam = np.dot(psiI,lam)

                # the lemma
                bar = np.dot(lamT,psiI)
                foo = np.linalg.inv(np.eye(self.M) + np.dot(lamT,psiIlam))
                self.inv_cov = psiI - np.dot(psiIlam,np.dot(foo,bar))
            else:
                # fix to lemma-like version
                self.inv_cov = np.linalg.inv(np.dot(lam,lamT))

    def run_inference(self,max_iter,check_factor,Nosc):

        check_iter = np.round(check_factor * self.N)

        count = 0
        nll_best = np.Inf
        nll = np.Inf
        for ii in range(max_iter):

            if (ii%check_iter)==0: 
                nll_new = self.total_negative_log_likelihood()
                print 'Iteration %d has neg. log likelhood %g' % (ii,nll_new)
                dlt_nll = nll - nll_new
                if nll_new<nll_best:
                    lam = self.lam
                    jitter = self.jitter
                    mean = self.mean
                    nll_best = nll_new
                if (dlt_nll<0.): 
                    count += 1
                    if count==Nosc:
                        self.mean = mean
                        self.lam = lam
                        self.jitter = jitter
                        self.nll = nll_best
                        break
                nll = nll_new
            if (ii%self.N)==0:
                ind = np.random.permutation(self.N)
                self.data = self.data[ind,:]
                self.obsvar = self.obsvar[ind,:]

            i = np.mod(ii,self.data.shape[0])            
            self.datum = self.data[i,:]
            self.variance = self.obsvar[i,:]

            self.invert_cov()
            self.make_gradient_step()

    def make_gradient_step(self):
        
        self.mean -= self.mean_rate * self.mean_gradients()
        self.jitter -= self.jitter_rate * self.jitter_gradients()
        self.lam -= self.lambda_rate * self.lambda_gradients()

        ind = (self.jitter < 0.0)
        self.jitter[ind] = 0.0
        
    def mean_gradients(self):
        """
        Numerical check ok.
        """
        return -2. * np.dot((self.datum - self.mean),self.inv_cov)
        
    def jitter_gradients(self):
        """
        Numerical check ok.
        """
        pt1 = np.dot(self.inv_cov.T,(self.datum - self.mean).T)
        pt2 = np.dot((self.datum - self.mean),self.inv_cov)
        return self.D * np.diag(self.inv_cov) - pt1 * pt2

    def lambda_gradients(self):
        pt1 = np.dot(self.inv_cov,self.lam) # d by m
        pt2 = np.zeros(self.M)
        for m in range(self.M):
            tmp = np.dot(self.inv_cov,self.lam[:,m])
            pt2[m] = np.dot((self.datum - self.mean),tmp) # scalar
        v = (self.datum - self.mean)[None,:] * pt2[:,None]
        pt2 = np.zeros((self.D,self.M))
        for m in range(self.M):
            pt2[:,m] = np.dot(self.inv_cov,v[m,:])
        return 2. * (self.D * pt1 - pt2)
    
    def total_negative_log_likelihood(self):
        totnll = 0.0
        for i in range(self.N):
            self.datum = self.data[i,:]
            self.variance = self.obsvar[i,:]
            self.invert_cov()
            totnll += self.single_negative_log_likelihood()
        return totnll
        
    def single_negative_log_likelihood(self):
        cov = self.make_cov()
        sgn, logdet = np.linalg.slogdet(cov)
        assert sgn>0
        pt1 = self.D * logdet
        xmm = self.datum - self.mean
        pt2 = np.dot(xmm,np.dot(self.inv_cov,xmm.T))
        return (pt1 + pt2)

    def make_cov(self):
        psi = np.diag(self.variance+self.jitter)
        lamlamT = np.dot(self.lam,self.lam.T)
        return psi+lamlamT

    def _check_gradients(self,Ncheck = 10):

        mgrad = self.mean_gradients()
        jgrad = self.jitter_gradients()
        lgrad = self.lambda_gradients()
        Dsamp = np.random.permutation(self.D)
        Msamp = np.random.permutation(self.M)
        
        for ii in range(Ncheck):

            i = np.mod(ii,self.D) 
            D = Dsamp[i]
            i = np.mod(ii,self.M) 
            M = Msamp[i]
            
            estm = self._check_one_gradient('mean',D)
            estj = self._check_one_gradient('jitter',D)
            estl = self._check_one_gradient('lambda',(D,M))
            
            print '\n\nCheck #%d, D = %d M = %d' % (ii,D,M)
            print '(Used mean grad., ' + \
                'Est. mean grad) = %g %g' % (mgrad[D],estm)
            print '(Used jitter grad., ' + \
                'Est. jitter grad) = %g %g' % (jgrad[D],estj)
            print '(Used lambda grad., ' + \
                'Est. lamda grad) = %g %g' % (lgrad[D,M],estl)

    def _check_one_gradient(self,kind,ind,eps = 1.0e-3):

        if kind=='mean':
            parm = self.mean
        elif kind=='jitter':
            parm = self.jitter
        else:
            parm = self.lam

        h = np.abs(parm[ind]) * eps
        if h==0.0: h = eps

        parm[ind] += h
        self.invert_cov()
        l1 = self.single_negative_log_likelihood()
        parm[ind] -= h
        self.invert_cov()
        l2 = self.single_negative_log_likelihood()

        return (l1 - l2) / (h)


