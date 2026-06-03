/**
 * Stub file for Capacitor native plugins.
 * Used in web builds where native device APIs are unavailable.
 * All exported members are no-ops so the app loads without crashing.
 */

// Generic stub for any named export
const noop = () => Promise.resolve({});
const noopObj: any = new Proxy({}, { get: () => noop });

export default noopObj;

// @capacitor/geolocation
export const Geolocation = {
  getCurrentPosition: () => Promise.resolve({ coords: { latitude: 0, longitude: 0, accuracy: 0 } }),
  watchPosition: () => ({ remove: noop }),
  clearWatch: noop,
  checkPermissions: () => Promise.resolve({ location: 'denied' }),
  requestPermissions: () => Promise.resolve({ location: 'denied' }),
};

// @capacitor/push-notifications
export const PushNotifications = {
  requestPermissions: () => Promise.resolve({ receive: 'denied' }),
  register: noop,
  addListener: () => ({ remove: noop }),
  removeAllListeners: noop,
  getDeliveredNotifications: () => Promise.resolve({ notifications: [] }),
  removeDeliveredNotifications: noop,
  removeAllDeliveredNotifications: noop,
  createChannel: noop,
  deleteChannel: noop,
  listChannels: () => Promise.resolve({ channels: [] }),
  checkPermissions: () => Promise.resolve({ receive: 'denied' }),
};

// @capacitor/background-runner
export const BackgroundRunner = {
  requestPermissions: noop,
  checkPermissions: () => Promise.resolve({}),
  dispatchEvent: noop,
};

// @capacitor-community/background-geolocation
export const BackgroundGeolocation = {
  addWatcher: () => Promise.resolve(''),
  removeWatcher: noop,
  openSettings: noop,
};

// Generic re-exports that some packages use
export const registerPlugin = () => noopObj;
export const Capacitor = { isNativePlatform: () => false, getPlatform: () => 'web' };
