import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_URL || '/api'

// Telegram WebApp initData
function getInitData() {
  if (typeof window !== 'undefined' && window.Telegram?.WebApp?.initData) {
    return window.Telegram.WebApp.initData
  }
  // Dev mode fallback
  return import.meta.env.VITE_DEV_INIT_DATA || ''
}

const api = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
})

// Har bir so'rovda initData headerini qo'shish
api.interceptors.request.use((config) => {
  const initData = getInitData()
  if (initData) {
    config.headers['X-Init-Data'] = initData
  }
  return config
})

export const usersApi = {
  getMe: () => api.get('/users/me'),
}

export const subscriptionApi = {
  get: () => api.get('/subscription/'),
  getHistory: () => api.get('/subscription/history'),
  createInvoice: () => api.post('/subscription/pay'),
}

export const commandsApi = {
  get: () => api.get('/commands/'),
  update: (command, value) => api.put('/commands/', { command, value }),
  reset: (command) => api.delete(`/commands/${command}`),
}

export const adminApi = {
  getUsers: (page = 1, limit = 20, search = '') =>
    api.get(`/admin/users?page=${page}&limit=${limit}${search ? `&search=${encodeURIComponent(search)}` : ''}`),
  getStats: () => api.get('/admin/stats'),
  getPending: () => api.get('/admin/pending'),
  getUserDetail: (id) => api.get(`/admin/user/${id}`),
  extendSub: (user_id, days) => api.post('/admin/extend_sub', { user_id, days }),
  toggleFree: (user_id, is_free) => api.post('/admin/toggle_free', { user_id, is_free }),
  banUser: (user_id, ban) => api.post('/admin/ban_user', { user_id, ban }),
}

export const statsApi = {
  get: () => api.get('/stats/'),
}

export const loginApi = {
  status:  ()  => api.get('/login/status'),
  request: ()  => api.post('/login/request'),
  check:   ()  => api.get('/login/check'),
  logout:  ()  => api.delete('/login/session'),
}

export default api
