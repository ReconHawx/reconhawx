import axios from 'axios';

// Always same-origin /api (local nginx :8080, k8s frontend nginx, Docker nginx strip /api for FastAPI).
// Do not use REACT_APP_API_URL here: CRA inlines it at compile time and a leaked env (e.g. api.url
// from shell or k8s manifests) becomes http://api:8000 / localhost:8000 and skips the /api proxy.
const API_BASE_URL = '/api';

// Export the base URL for use in other components
export { API_BASE_URL };

const api = axios.create({
    baseURL: API_BASE_URL,
    headers: {
        'Content-Type': 'application/json',
    },
});

api.interceptors.request.use(
    (config) => {
        const token = localStorage.getItem('access_token');
        if (token) {
            config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
    },
    (error) => {
        return Promise.reject(error);
    }
);

api.interceptors.response.use(
    (response) => response,
    async (error) => {
        const originalRequest = error.config;

        if (error.response?.status === 401 && !originalRequest._retry) {
            originalRequest._retry = true;

            try {
                // Try to refresh the token
                const refreshToken = localStorage.getItem('refresh_token');
                if (refreshToken) {
                    const response = await api.post('/auth/refresh', {
                        refresh_token: refreshToken
                    });

                    const { access_token } = response.data;
                    localStorage.setItem('access_token', access_token);
                    localStorage.setItem('token_expires_at', Date.now() + (response.data.expires_in * 1000));

                    // Update the failed request with new token
                    originalRequest.headers.Authorization = `Bearer ${access_token}`;
                    return api(originalRequest);
                }
            } catch (refreshError) {
                // Refresh failed, redirect to login
                localStorage.removeItem('access_token');
                localStorage.removeItem('refresh_token');
                localStorage.removeItem('user_data');
                localStorage.removeItem('token_expires_at');
                window.location.href = '/login';
                return Promise.reject(refreshError);
            }
        }

        return Promise.reject(error);
    }
);

export { api };
