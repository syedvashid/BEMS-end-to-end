import axios from 'axios'
import { session } from './session'

export const DEV_AUTH = import.meta.env.VITE_DEV_AUTH === 'true'

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 20000,
})

api.interceptors.request.use((config) => {
  console.log('REQ', config.url, { DEV_AUTH, user: session.username, fac: session.facilityId })
  if (DEV_AUTH) {
    if (session.username) config.headers['X-Dev-User'] = session.username
    if (session.facilityId) config.headers['X-Facility-Id'] = session.facilityId
  }
  return config
})