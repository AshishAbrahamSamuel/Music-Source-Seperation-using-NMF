import numpy as np

from criterion.divergence import generalized_kl_divergence, is_divergence, multichannel_is_divergence
from algorithm.linalg import solve_Riccati

EPS=1e-12

__metrics__ = ['EUC', 'KL', 'IS']

class NMFbase:
    def __init__(self, n_basis=2, eps=EPS):
        """
        Args:
            n_basis: number of basis
        """

        self.n_basis = n_basis
        self.loss = []

        self.eps = eps
    
    def __call__(self, target, iteration=100, **kwargs):
        self.target = target

        self._reset(**kwargs)

        self.update(iteration=iteration)

        T, V = self.basis, self.activation

        return T.copy(), V.copy()
    
    def _reset(self, **kwargs):
        assert self.target is not None, "Specify data!"

        for key in kwargs.keys():
            setattr(self, key, kwargs[key])
        
        n_basis = self.n_basis
        n_bins, n_frames = self.target.shape

        self.basis = np.random.rand(n_bins, n_basis)
        self.activation = np.random.rand(n_basis, n_frames)
    
    def update(self, iteration=100):
        target = self.target

        for idx in range(iteration):
            self.update_once()

            TV = self.basis @ self.activation
            loss = self.criterion(TV, target)
            self.loss.append(loss.sum())
        
    def update_once(self):
        raise NotImplementedError("Implement 'update_once' function")

class ComplexNMFbase:
    def __init__(self, n_basis=2, regularizer=0.1, eps=EPS):
        """
        Args:
            n_basis: number of basis
        """

        self.n_basis = n_basis
        self.regularizer = regularizer
        self.loss = []

        self.eps = eps
    
    def __call__(self, target, iteration=100, **kwargs):
        self.target = target

        self._reset(**kwargs)
        
        self.update(iteration=iteration)

        T, V = self.basis, self.activation
        Phi = self.phase

        return T.copy(), V.copy(), Phi.copy()
    
    def _reset(self, **kwargs):
        assert self.target is not None, "Specify data!"

        for key in kwargs.keys():
            setattr(self, key, kwargs[key])
        
        n_basis = self.n_basis
        n_bins, n_frames = self.target.shape

        self.basis = np.random.rand(n_bins, n_basis)
        self.activation = np.random.rand(n_basis, n_frames)
        self.phase = 2 * np.pi * np.random.rand(n_bins, n_basis, n_frames)

    def init_phase(self):
        n_basis = self.n_basis
        target = self.target

        phase = np.angle(target)
        self.phase = np.tile(phase[:,np.newaxis,:], reps=(1, n_basis, 1))
    
    def update(self, iteration=100):
        target = self.target

        for idx in range(iteration):
            self.update_once()

            TVPhi = np.sum(self.basis[:,:,np.newaxis] * self.activation[:,np.newaxis,:] * self.phase, axis=1)
            loss = self.criterion(TVPhi, target)
            self.loss.append(loss.sum())
        
    def update_once(self):
        raise NotImplementedError("Implement 'update_once' method")

class MultichannelNMFbase:
    def __init__(self, n_basis=2, eps=EPS):
        """
        Args:
            n_basis: number of basis
        """

        self.n_basis = n_basis
        self.loss = []

        self.eps = eps
    
    def __call__(self, target, iteration=100, **kwargs):
        self.target = target

        self._reset(**kwargs)
        
        self.update(iteration=iteration)
    
    def _reset(self, **kwargs):
        assert self.target is not None, "Specify data!"

        for key in kwargs.keys():
            setattr(self, key, kwargs[key])
    
    def update(self, iteration=100):
        for idx in range(iteration):
            self.update_once()
        
        raise NotImplementedError("Implement `update` method.")
    
    def update_once(self):
        raise NotImplementedError("Implement `update_once` method.")

class EUCNMF(NMFbase):
    def __init__(self, n_basis=2, domain=2, algorithm='mm', eps=EPS):
        """
        Args:
            n_basis: number of basis
        """
        super().__init__(n_basis=n_basis, eps=eps)

        assert 1 <= domain <= 2, "1 <= `domain` <= 2 is not satisfied."
        assert algorithm == 'mm', "algorithm must be 'mm'."

        self.domain = domain
        self.algorithm = algorithm
        self.criterion = lambda input, target: (target - input)**2
    
    def update(self, iteration=100):
        domain = self.domain
        target = self.target

        for idx in range(iteration):
            self.update_once()

            TV = (self.basis @ self.activation)**(2 / domain)
            loss = self.criterion(TV, target)
            self.loss.append(loss.sum())

    def update_once(self):
        if self.algorithm == 'mm':
            self.update_once_mm()
        else:
            raise ValueError("Not support {} based update.".format(self.algorithm))
    
    def update_once_mm(self):
        target = self.target
        domain = self.domain
        eps = self.eps

        T, V = self.basis, self.activation

        # Update basis
        V_transpose = V.transpose(1,0)
        TV = T @ V
        TV[TV < eps] = eps
        TVV = (TV**((4 - domain) / domain)) @ V_transpose
        TVV[TVV < eps] = eps
        numerator = (target * (TV**((2 - domain) / domain))) @ V_transpose
        T = T * (numerator / TVV)**(domain / (4 - domain))

        # Update activations
        T_transpose = T.transpose(1,0)
        TV = T @ V
        TV[TV < eps] = eps
        TTV = T_transpose @ (TV**((4 - domain) / domain))
        TTV[TTV < eps] = eps
        numerator = T_transpose @ (target * (TV**((2 - domain) / domain)))
        V = V * (numerator / TTV)**(domain / (4 - domain))

        self.basis, self.activation = T, V

class KLNMF(NMFbase):
    def __init__(self, n_basis=2, domain=2, algorithm='mm', eps=EPS):
        """
        Args:
            K: number of basis
        """
        super().__init__(n_basis=n_basis, eps=eps)

        assert 1 <= domain <= 2, "1 <= `domain` <= 2 is not satisfied."
        assert algorithm == 'mm', "algorithm must be 'mm'."

        self.domain = domain
        self.algorithm = algorithm
        self.criterion = generalized_kl_divergence
    
    def update(self, iteration=100):
        domain = self.domain
        target = self.target

        for idx in range(iteration):
            self.update_once()

            TV = (self.basis @ self.activation)**(2 / domain)
            loss = self.criterion(TV, target)
            self.loss.append(loss.sum())
    
    def update_once(self):
        if self.algorithm == 'mm':
            self.update_once_mm()
        else:
            raise ValueError("Not support {} based update.".format(self.algorithm))

    def update_once_mm(self):
        target = self.target
        domain = self.domain
        eps = self.eps

        T, V = self.basis, self.activation

        # Update basis
        V_transpose = V.transpose(1,0)
        TV = T @ V
        TV[TV < eps] = eps
        TVV = (TV**((2 - domain) / domain)) @ V_transpose
        TVV[TVV < eps] = eps
        division = target / TV
        T = T * (division @ V_transpose / TVV)**(domain / 2)

        # Update activations
        T_transpose = T.transpose(1,0)
        TV = T @ V
        TV[TV < eps] = eps
        TTV = T_transpose @ (TV**((2 - domain) / domain))
        TTV[TTV < eps] = eps
        division = target / TV
        V = V * (T_transpose @ division / TTV)**(domain / 2)

        self.basis, self.activation = T, V

class ISNMF(NMFbase):
    def __init__(self, n_basis=2, domain=2, algorithm='mm', eps=EPS):
        """
        Args:
            K: number of basis
            algorithm: 'mm': MM algorithm based update
        """
        super().__init__(n_basis=n_basis, eps=eps)

        assert 1 <= domain <= 2, "1 <= `domain` <= 2 is not satisfied."

        self.domain = domain
        self.algorithm = algorithm
        self.criterion = is_divergence
    
    def update(self, iteration=100):
        domain = self.domain
        target = self.target

        for idx in range(iteration):
            self.update_once()

            TV = (self.basis @ self.activation)**(2 / domain)
            loss = self.criterion(TV, target)
            self.loss.append(loss.sum())

    def update_once(self):
        if self.algorithm == 'mm':
            self.update_once_mm()
        elif self.algorithm == 'me':
            self.update_once_me()
        else:
            raise ValueError("Not support {} based update.".format(self.algorithm))
    
    def update_once_mm(self):
        target = self.target
        domain = self.domain
        eps = self.eps

        T, V = self.basis, self.activation

        # Update basis
        V_transpose = V.transpose(1,0)
        TV = T @ V
        TV[TV < eps] = eps
        division, TV_inverse = target / (TV**((domain + 2) / domain)), 1 / TV
        TVV = TV_inverse @ V_transpose
        TVV[TVV < eps] = eps
        T = T * (division @ V_transpose / TVV)**(domain / (domain + 2))

        # Update activations
        T_transpose = T.transpose(1,0)
        TV = T @ V
        TV[TV < eps] = eps
        division, TV_inverse = target / (TV**((domain + 2) / domain)), 1 / TV
        TTV = T_transpose @ TV_inverse
        TTV[TTV < eps] = eps
        V = V * (T_transpose @ division / TTV)**(domain / (domain + 2))

        self.basis, self.activation = T, V
    
    def update_once_me(self):
        target = self.target
        domain = self.domain
        eps = self.eps

        assert domain == 2, "Only domain = 2 is supported."

        T, V = self.basis, self.activation

        # Update basis
        V_transpose = V.transpose(1,0)
        TV = T @ V
        TV[TV < eps] = eps
        division, TV_inverse = target / (TV**((domain + 2) / domain)), 1 / TV
        TVV = TV_inverse @ V_transpose
        TVV[TVV < eps] = eps
        T = T * (division @ V_transpose / TVV)

        # Update activations
        T_transpose = T.transpose(1,0)
        TV = T @ V
        TV[TV < eps] = eps
        division, TV_inverse = target / (TV**((domain + 2) / domain)), 1 / TV
        TTV = T_transpose @ TV_inverse
        TTV[TTV < eps] = eps
        V = V * (T_transpose @ division / TTV)

        self.basis, self.activation = T, V

class tNMF(NMFbase):
    def __init__(self, n_basis=2, nu=1e+3, domain=2, algorithm='mm', eps=EPS):
        """
        Args:
            K: number of basis
            algorithm: 'mm': MM algorithm based update
        """
        super().__init__(n_basis=n_basis, eps=eps)

        def t_divergence(input, target):
            # TODO: implement criterion
            _input, _target = input + eps, target + eps
            
            return np.log(_input) + (2 + self.nu) / 2 * np.log(1 + (2 / nu) * (_target / _input))

        assert 1 <= domain <= 2, "1 <= `domain` <= 2 is not satisfied."

        self.nu = nu
        self.domain = domain
        self.algorithm = algorithm
        self.criterion = t_divergence
    
    def update(self, iteration=100):
        domain = self.domain
        target = self.target

        for idx in range(iteration):
            self.update_once()

            TV = (self.basis @ self.activation)**(2 / domain)
            loss = self.criterion(TV, target)
            self.loss.append(loss.sum())

    def update_once(self):
        if self.algorithm == 'mm':
            self.update_once_mm()
        else:
            raise ValueError("Not support {} based update.".format(self.algorithm))
    
    def update_once_mm(self):
        target = self.target
        domain = self.domain
        nu = self.nu
        eps = self.eps

        assert domain == 2, "`domain` is expected 2."

        T, V = self.basis, self.activation
        Z = np.maximum(target, eps)

        # Update basis
        V_transpose = V.transpose(1, 0)
        TV = T @ V
        TV[TV < eps] = eps
        harmonic = 1 / (2 / ((2 + nu) * TV) + nu / ((2 + nu) * Z))
        division, TV_inverse = harmonic / (TV**2), 1 / TV
        TVV = TV_inverse @ V_transpose
        TVV[TVV < eps] = eps
        T = T * np.sqrt(division @ V_transpose / TVV)

        # Update activations
        T_transpose = T.transpose(1, 0)
        TV = T @ V
        TV[TV < eps] = eps
        harmonic = 1 / (2 / ((2 + nu) * TV) + nu / ((2 + nu) * Z))
        division, TV_inverse = harmonic / (TV**2), 1 / TV
        TTV = T_transpose @ TV_inverse
        TTV[TTV < eps] = eps
        V = V * np.sqrt(T_transpose @ division / TTV)

        self.basis, self.activation = T, V

class CauchyNMF(NMFbase):
    def __init__(self, n_basis, domain=2, algorithm='naive-multipricative', eps=EPS):
        super().__init__(n_basis=n_basis, eps=eps)

        def cauchy_divergence(input, target):
            eps = self.eps

            _input, _target = input + eps, target + eps
            numerator = 2 * _target**2 + _input**2
            denominator = 3 * _target**2
            
            return np.log(_target / _input) + (3 / 2) * np.log(numerator / denominator)

        assert domain == 2, "Only `domain` = 2 is supported."

        self.domain = domain
        self.algorithm = algorithm
        self.criterion = cauchy_divergence
    
    def update_once(self):
        if self.algorithm == 'naive-multipricative':
            self.update_once_naive()
        elif self.algorithm == 'mm':
            self.update_once_mm()
        elif self.algorithm == 'me':
            self.update_once_me()
        elif self.algorithm == 'mm_fast':
            self.update_once_mm_fast()
        else:
            raise ValueError("Not support {} based update.".format(self.algorithm))

    def update_once_naive(self):
        """
        Cauchy Nonnegative Matrix Factorization
        See https://hal.inria.fr/hal-01170924/document
        """
        target = self.target
        domain = self.domain
        eps = self.eps

        assert domain == 2, "Only 'domain' = 2 is supported."

        T, V = self.basis, self.activation

        TV = T @ V
        TV[TV < eps] = eps
        numerator = np.sum(V[np.newaxis,:,:] / TV[:,np.newaxis,:], axis=2)
        C = 2 * target + TV**2
        C[C < eps] = eps
        TVC = TV / C
        denominator = 3 * TVC @ V.transpose(1, 0)
        denominator[denominator < eps] = eps
        T = T * (numerator / denominator)

        TV = T @ V
        TV[TV < eps] = eps
        numerator = np.sum(T[:,:, np.newaxis] / TV[:,np.newaxis,:], axis=0)
        C = 2 * target + TV**2
        C[C < eps] = eps
        TVC = TV / C
        denominator = 3 * T.transpose(1, 0) @ TVC
        denominator[denominator < eps] = eps
        V = V * (numerator / denominator)

        self.basis, self.activation = T, V

    def update_once_mm(self):
        target = self.target
        domain = self.domain
        eps = self.eps

        assert domain == 2, "Only 'domain' = 2 is supported."

        T, V = self.basis, self.activation

        TV = T @ V
        TV[TV < eps] = eps
        numerator = np.sum(V[np.newaxis,:,:] / TV[:,np.newaxis,:], axis=2)
        C = 2 * target + TV**2
        C[C < eps] = eps
        TVC = TV / C
        denominator = 3 * TVC @ V.transpose(1, 0)
        denominator[denominator < eps] = eps
        T = T * np.sqrt(numerator / denominator)

        TV = T @ V
        TV[TV < eps] = eps
        numerator = np.sum(T[:,:, np.newaxis] / TV[:,np.newaxis,:], axis=0)
        C = 2 * target + TV**2
        C[C < eps] = eps
        TVC = TV / C
        denominator = 3 * T.transpose(1, 0) @ TVC
        denominator[denominator < eps] = eps
        V = V * np.sqrt(numerator / denominator)

        self.basis, self.activation = T, V
    
    def update_once_me(self):
        """
        Cauchy Nonnegative Matrix Factorization
        See https://hal.inria.fr/hal-01170924/document
        """
        target = self.target
        domain = self.domain
        eps = self.eps

        assert domain == 2, "Only 'domain' = 2 is supported."

        T, V = self.basis, self.activation
        
        TV = T @ V
        TV2Z = TV**2 + target
        TV2Z[TV2Z < eps] = eps
        A = (3 / 4) * (TV / TV2Z) @ V.transpose(1, 0)
        B = np.sum(V[np.newaxis,:,:] / TV[:,np.newaxis,:], axis=2)
        denominator = A + np.sqrt(A**2 + 2 * B * A)
        denominator[denominator < eps] = eps
        T = T * (B / denominator)

        TV = T @ V
        TV2Z = TV**2 + target
        TV2Z[TV2Z < eps] = eps
        A = (3 / 4) * T.transpose(1, 0) @ (TV / TV2Z)
        B = np.sum(T[:,:,np.newaxis] / TV[:,np.newaxis,:], axis=0)
        denominator = A + np.sqrt(A**2 + 2 * B * A)
        denominator[denominator < eps] = eps
        V = V * (B / denominator)

        self.basis, self.activation = T, V

    def update_once_mm_fast(self):
        target = self.target
        domain = self.domain
        eps = self.eps

        assert domain == 2, "Only 'domain' = 2 is supported."

        T, V = self.basis, self.activation

        # Update basis
        TV = T @ V
        C = 2 * target + TV**2
        CTV = C * TV
        CTV[CTV < eps] = eps
        ZCTV = target / CTV
        C[C < eps] = eps
        TVC = TV / C
        numerator = ZCTV @ V.transpose(1, 0)
        denominator = TVC @ V.transpose(1, 0)
        denominator[denominator < eps] = eps
        T = T * np.sqrt(numerator / denominator)

        # Update basis
        TV = T @ V
        C = 2 * target + TV**2
        CTV = C * TV
        CTV[CTV < eps] = eps
        ZCTV = target / CTV
        C[C < eps] = eps
        TVC = TV / C
        numerator = T.transpose(1, 0) @ ZCTV
        denominator = T.transpose(1, 0) @ TVC
        denominator[denominator < eps] = eps
        V = V * np.sqrt(numerator / denominator)

        self.basis, self.activation = T, V

class ComplexEUCNMF(ComplexNMFbase):
    def __init__(self, n_basis=2, regularizer=0.1, p=1, eps=EPS):
        """
        Args:
            n_basis: number of basis
        """
        super().__init__(n_basis=n_basis, eps=eps)

        self.criterion = lambda input, target: np.abs(input - target)**2
        self.regularizer, self.p = regularizer, p
    
    def _reset(self, **kwargs):
        super()._reset(**kwargs)

        self.init_phase()
        self.update_beta()
    
    def update(self, iteration=100):
        target = self.target

        for idx in range(iteration):
            self.update_once()

            TVPhi = np.sum(self.basis[:,:,np.newaxis] * self.activation[np.newaxis,:,:] * self.phase, axis=1)
            loss = self.criterion(TVPhi, target)
            self.loss.append(loss.sum())
    
    def update_once(self):
        target = self.target
        regularizer, p = self.regularizer, self.p
        eps = self.eps

        T, V, Phi = self.basis, self.activation, self.phase
        Ephi = np.exp(1j * Phi)
        Beta = self.Beta
        Beta[Beta < eps] = eps

        X = T[:,:,np.newaxis] * V[np.newaxis,:,:] * Ephi
        ZX = target - X.sum(axis=1)
        
        Z_bar = X + Beta * ZX[:,np.newaxis,:]
        V_bar = V
        V_bar[V_bar < eps] = eps
        Re = np.real(Z_bar.conj() * Ephi)

        # Update basis
        VV = V**2
        numerator = (V[np.newaxis,:,:] / Beta) * Re
        numerator = numerator.sum(axis=2)
        denominator = np.sum(VV[np.newaxis,:,:] / Beta, axis=2) # (n_bins, n_basis)
        denominator[denominator < eps] = eps
        T = numerator / denominator

        # Update activations
        TT = T**2
        numerator = (T[:,:,np.newaxis] / Beta) * Re
        numerator = numerator.sum(axis=0)
        denominator = np.sum(TT[:,:,np.newaxis] / Beta, axis=0) + regularizer * p * V_bar**(p - 2) # (n_basis, n_frames)
        denominator[denominator < eps] = eps
        V = numerator / denominator

        # Update phase    
        phase = np.angle(Z_bar)

        # Normalize basis
        T = T / T.sum(axis=0)

        self.basis, self.activation, self.phase = T, V, phase

        # Update beta
        self.update_beta()
    
    def update_beta(self):
        T, V = self.basis[:,:,np.newaxis], self.activation[np.newaxis,:,:]
        eps = self.eps

        TV = T * V # (n_bins, n_basis, n_frames)
        TVsum = TV.sum(axis=1, keepdims=True)
        TVsum[TVsum < eps] = eps
        self.Beta = TV / TVsum

class MultichannelISNMF(MultichannelNMFbase):
    """
    Reference: "Multichannel Extensions of Non-Negative Matrix Factorization With Complex-Valued Data"
    See https://ieeexplore.ieee.org/document/5229304
    """
    def __init__(self, n_basis=10, normalize=True, eps=EPS):
        """
        Args:
            n_basis
            eps <float>: Machine epsilon
        """
        super().__init__(n_basis=n_basis, eps=eps)

        self.criterion = multichannel_is_divergence
        self.normalize = normalize
    
    def __call__(self, target, iteration=100, **kwargs):
        self.target = target

        self._reset(**kwargs)

        self.update(target, iteration=iteration)

        H, T, V = self.spatial, self.basis, self.activation

        return H.copy(), T.copy(), V.copy()
    
    def _reset(self, **kwargs):
        super()._reset(**kwargs)

        n_basis = self.n_basis
        n_bins, n_frames, n_channels, _n_channels = self.target.shape

        assert _n_channels == n_channels, "Invalid input shape"

        self.n_bins, self.n_frames = n_bins, n_frames
        self.n_channels = n_channels
    
        if not hasattr(self, 'spatial'):
            H = np.eye(n_channels)
            self.spatial = np.tile(H, reps=(n_bins, n_basis, 1, 1))
        else:
            self.spatial = self.spatial.copy()
        if not hasattr(self, 'basis'):
            self.basis = np.random.rand(n_bins, n_basis)
        else:
            self.basis = self.basis.copy()
        if not hasattr(self, 'activation'):
            self.activation = np.random.rand(n_basis, n_frames)
        else:
            self.activation = self.activation.copy()

    def update(self, target, iteration=100):
        for idx in range(iteration):
            self.update_once()

            HTV = self.reconstruct()
            loss = self.criterion(HTV, target)
            self.loss.append(loss.sum())
    
    def update_once(self):
        self.update_basis()
        self.update_activation()
        self.update_spatial()
    
    def update_basis(self):
        n_channels = self.n_channels
        eps = self.eps

        X = self.target # (n_bins, n_frames, n_channels, n_channels)
        H = self.spatial # (n_bins, n_basis, n_channels, n_channels)
        T, V = self.basis, self.activation # (n_bins, n_basis), (n_basis, n_frames)

        X_hat = self.reconstruct()
        inv_X_hat = np.linalg.inv(X_hat + eps * np.eye(n_channels)) # (n_bins, n_frames, n_channels, n_channels)
        XXX = inv_X_hat @ X @ inv_X_hat # (n_bins, n_frames, n_channels, n_channels)
        
        numerator = np.trace(XXX[:, np.newaxis, :, :, :] @ H[:, :, np.newaxis, :, :], axis1=-2, axis2=-1).real # (n_bins, 1, n_frames, n_channels, n_channels), (n_bins, n_basis, 1, n_channels, n_channels) -> (n_bins, n_basis, n_frames)
        numerator = np.sum(V * numerator, axis=2) # (n_bins, n_basis)
        denominator = np.trace(inv_X_hat[:, np.newaxis, :, :, :] @ H[:, :, np.newaxis, :, :], axis1=-2, axis2=-1).real # (n_bins, 1, n_frames, n_channels, n_channels), (n_bins, n_basis, 1, n_channels, n_channels) -> (n_bins, n_basis, n_frames)
        denominator = np.sum(V * denominator, axis=2) # (n_bins, n_basis, n_basis)
        denominator[denominator < eps] = eps

        T = T * np.sqrt(numerator / denominator)
        self.basis = T

    def update_activation(self):
        n_channels = self.n_channels
        eps = self.eps

        X = self.target # (n_bins, n_frames, n_channels, n_channels)
        H = self.spatial # (n_bins, n_basis, n_channels, n_channels)
        T, V = self.basis, self.activation # (n_bins, n_basis), (n_basis, n_frames)

        X_hat = self.reconstruct()
        inv_X_hat = np.linalg.inv(X_hat + eps * np.eye(n_channels)) # (n_bins, n_frames, n_channels, n_channels)
        XXX = inv_X_hat @ X @ inv_X_hat # (n_bins, n_frames, n_channels, n_channels)

        numerator = np.trace(XXX[:, np.newaxis, :, :, :] @ H[:, :, np.newaxis, :, :], axis1=-2, axis2=-1).real # (n_bins, 1, n_frames, n_channels, n_channels), (n_bins, n_basis, 1, n_channels, n_channels) -> (n_bins, n_basis, n_frames)
        numerator = np.sum(T[:, :, np.newaxis] * numerator, axis=0) # (n_basis, n_frames)
        denominator = np.trace(inv_X_hat[:, np.newaxis, :, :, :] @ H[:, :, np.newaxis, :, :], axis1=-2, axis2=-1).real # (n_bins, 1, n_frames, n_channels, n_channels), (n_bins, n_basis, 1, n_channels, n_channels) -> (n_bins, n_basis, n_frames)
        denominator = np.sum(T[:, :, np.newaxis] * denominator, axis=0) # (n_basis, n_frames)
        denominator[denominator < eps] = eps

        V = V * np.sqrt(numerator / denominator)
        self.activation = V
    
    def update_spatial(self):
        n_channels = self.n_channels
        eps = self.eps

        X = self.target # (n_bins, n_frames, n_channels, n_channels)
        H = self.spatial # (n_bins, n_basis, n_channels, n_channels)
        T, V = self.basis, self.activation # (n_bins, n_basis), (n_basis, n_frames)

        X_hat = self.reconstruct()
        inv_X_hat = np.linalg.inv(X_hat + eps * np.eye(n_channels)) # (n_bins, n_frames, n_channels, n_channels)
        XXX = inv_X_hat @ X @ inv_X_hat # (n_bins, n_frames, n_channels, n_channels)
        VXXX = np.sum(V[np.newaxis, :, :, np.newaxis, np.newaxis] * XXX[:, np.newaxis, :, :, :], axis=2) # (n_bins, n_basis, n_channels, n_channels)
        
        A = np.sum(V[np.newaxis, :, :, np.newaxis, np.newaxis] * inv_X_hat[:, np.newaxis, :, :, :], axis=2) # (n_bins, nbasis, n_channels, n_channels)
        B = H @ VXXX @ H
        H = solve_Riccati(A, B)
        H = H + eps * np.eye(n_channels)

        if self.normalize:
            H = H / np.trace(H, axis1=2, axis2=3)[..., np.newaxis, np.newaxis]
            
        self.spatial = H
    
    def reconstruct(self):
        H = self.spatial # (n_bins, n_basis, n_channels, n_channels)
        T, V = self.basis, self.activation # (n_bins, n_basis), (n_basis, n_frames)

        TV = T[:, :, np.newaxis] * V[np.newaxis, :, :] # (n_bins, n_basis, n_frames)
        X_hat = np.sum(H[:, :, np.newaxis, :, :] * TV[:, :, :, np.newaxis, np.newaxis], axis=1) # (n_bins, n_frames, n_channels, n_channels)
        
        return X_hat

"""
    TODO
    - "Itakura-Saito nonnegative matrix factorization with group sparsity", https://ieeexplore.ieee.org/document/5946318
    - NMF with beta divergence
    - NMF with Bregman divergence
"""

def _test(metric='EUC', algorithm='mm'):
    np.random.seed(111)

    fft_size, hop_size = 1024, 256
    n_basis = 6
    domain = 2
    iteration = 100
    
    signal, sr = read_wav("data/single-channel/music-8000.wav")
    
    T = len(signal)

    spectrogram = stft(signal, fft_size=fft_size, hop_size=hop_size)
    amplitude = np.abs(spectrogram)
    power = amplitude**2

    if metric == 'EUC':
        iteration = 80
        nmf = EUCNMF(n_basis, domain=domain, algorithm=algorithm)
    elif metric == 'KL':
        iteration = 50
        domain = 1.5
        nmf = KLNMF(n_basis, domain=domain, algorithm=algorithm)
    elif metric == 'IS':
        iteration = 50
        nmf = ISNMF(n_basis, domain=domain, algorithm=algorithm)
    elif metric == 't':
        iteration = 50
        nu = 100
        nmf = tNMF(n_basis, nu=nu, domain=domain, algorithm=algorithm)
    elif metric == 'Cauchy':
        iteration = 20
        nmf = CauchyNMF(n_basis, domain=domain, algorithm=algorithm)
    else:
        raise NotImplementedError("Not support {}-NMF".format(metric))

    basis, activation = nmf(power, iteration=iteration)

    amplitude[amplitude < EPS] = EPS

    estimated_power = (basis @ activation)**(2 / domain)
    estimated_amplitude = np.sqrt(estimated_power)
    ratio = estimated_amplitude / amplitude
    estimated_spectrogram = ratio * spectrogram
    
    estimated_signal = istft(estimated_spectrogram, fft_size=fft_size, hop_size=hop_size, length=T)
    estimated_signal = estimated_signal / np.abs(estimated_signal).max()
    write_wav("data/NMF/{}/{}/music-8000-estimated-iter{}.wav".format(metric, algorithm, iteration), signal=estimated_signal, sr=sr)

    power[power < EPS] = EPS
    log_spectrogram = 10 * np.log10(power)

    plt.figure()
    plt.pcolormesh(log_spectrogram, cmap='jet')
    plt.colorbar()
    plt.savefig('data/NMF/spectrogram.png', bbox_inches='tight')
    plt.close()

    for idx in range(n_basis):
        estimated_power = (basis[:, idx: idx+1] @ activation[idx: idx+1, :])**(2 / domain)
        estimated_amplitude = np.sqrt(estimated_power)
        ratio = estimated_amplitude / amplitude
        estimated_spectrogram = ratio * spectrogram

        estimated_signal = istft(estimated_spectrogram, fft_size=fft_size, hop_size=hop_size, length=T)
        estimated_signal = estimated_signal / np.abs(estimated_signal).max()
        write_wav("data/NMF/{}/{}/music-8000-estimated-iter{}-{}.wav".format(metric, algorithm, iteration, idx), signal=estimated_signal, sr=sr)

        estimated_power[estimated_power < EPS] = EPS
        log_spectrogram = 10 * np.log10(estimated_power)

        plt.figure()
        plt.pcolormesh(log_spectrogram, cmap='jet')
        plt.colorbar()
        plt.savefig('data/NMF/{}/{}/estimated-spectrogram-iter{}-basis{}.png'.format(metric, algorithm, iteration, idx), bbox_inches='tight')
        plt.close()
    
    plt.figure()
    plt.plot(nmf.loss, color='black')
    plt.xlabel('Iteration')
    plt.ylabel('Loss')
    plt.savefig('data/NMF/{}/{}/loss.png'.format(metric, algorithm), bbox_inches='tight')
    plt.close()

def _test_cnmf(metric='EUC'):
    np.random.seed(111)

    fft_size, hop_size = 1024, 256
    n_basis = 6
    p = 1.2
    iteration = 100
    
    signal, sr = read_wav("data/single-channel/music-8000.wav")
    T = len(signal)
    spectrogram = stft(signal, fft_size=fft_size, hop_size=hop_size)
    
    regularizer = 1e-5 * np.sum(np.abs(spectrogram)**2) / (n_basis**(1 - 2 / p))
    
    if metric == 'EUC':
        nmf = ComplexEUCNMF(n_basis, regularizer=regularizer, p=p)
    else:
        raise NotImplementedError("Not support {}-NMF".format(metric))
    
    basis, activation, phase = nmf(spectrogram, iteration=iteration)

    estimated_spectrogram = basis[:,:,np.newaxis] * activation[np.newaxis,:,:] * np.exp(1j*phase)
    estimated_spectrogram = estimated_spectrogram.sum(axis=1)
    estimated_signal = istft(estimated_spectrogram, fft_size=fft_size, hop_size=hop_size, length=T)
    estimated_signal = estimated_signal / np.abs(estimated_signal).max()
    write_wav("data/CNMF/{}/music-8000-estimated-iter{}.wav".format(metric, iteration), signal=estimated_signal, sr=sr)

    estimated_power = np.abs(estimated_spectrogram)**2
    estimated_power[estimated_power < EPS] = EPS
    log_spectrogram = 10 * np.log10(estimated_power)

    plt.figure()
    plt.pcolormesh(log_spectrogram, cmap='jet')
    plt.colorbar()
    plt.savefig('data/CNMF/spectrogram.png', bbox_inches='tight')
    plt.close()

    for idx in range(n_basis):
        estimated_spectrogram = basis[:, idx: idx + 1] * activation[idx: idx + 1, :] * phase[:, idx, :]

        estimated_signal = istft(estimated_spectrogram, fft_size=fft_size, hop_size=hop_size, length=T)
        estimated_signal = estimated_signal / np.abs(estimated_signal).max()
        write_wav("data/CNMF/{}/music-8000-estimated-iter{}-basis{}.wav".format(metric, iteration, idx), signal=estimated_signal, sr=sr)

        estimated_power = np.abs(estimated_spectrogram)**2
        estimated_power[estimated_power < EPS] = EPS
        log_spectrogram = 10 * np.log10(estimated_power)

        plt.figure()
        plt.pcolormesh(log_spectrogram, cmap='jet')
        plt.colorbar()
        plt.savefig('data/CNMF/{}/estimated-spectrogram-iter{}-basis{}.png'.format(metric, iteration, idx), bbox_inches='tight')
        plt.close()
    
    plt.figure()
    plt.plot(nmf.loss, color='black')
    plt.xlabel('Iteration')
    plt.ylabel('Loss')
    plt.savefig('data/CNMF/{}/loss.png'.format(metric), bbox_inches='tight')
    plt.close()

if __name__ == '__main__':
    import numpy as np
    import os
    import matplotlib.pyplot as plt
    
    from utils.utils_audio import read_wav, write_wav
    from transform.stft import stft, istft

    plt.rcParams['figure.dpi'] = 200

    # "Real" NMF
    os.makedirs('data/NMF/EUC/mm', exist_ok=True)
    os.makedirs('data/NMF/KL/mm', exist_ok=True)
    os.makedirs('data/NMF/IS/mm', exist_ok=True)
    os.makedirs('data/NMF/IS/me', exist_ok=True)
    os.makedirs('data/NMF/t/mm', exist_ok=True)
    os.makedirs('data/NMF/Cauchy/naive-multipricative', exist_ok=True)
    os.makedirs('data/NMF/Cauchy/mm', exist_ok=True)
    os.makedirs('data/NMF/Cauchy/me', exist_ok=True)
    os.makedirs('data/NMF/Cauchy/mm_fast', exist_ok=True)

    _test(metric='EUC', algorithm='mm')
    _test(metric='KL', algorithm='mm')
    _test(metric='IS', algorithm='mm')
    _test(metric='IS', algorithm='me')
    _test(metric='t', algorithm='mm')
    _test(metric='Cauchy', algorithm='naive-multipricative')
    _test(metric='Cauchy', algorithm='mm')
    _test(metric='Cauchy', algorithm='me')
    _test(metric='Cauchy', algorithm='mm_fast')

    # Complex NMF
    os.makedirs('data/CNMF/EUC', exist_ok=True)

    _test_cnmf(metric='EUC')