// Background location runner — fires every 30 minutes via Android WorkManager.
// Two events:
//   setTechId   — called from main app on login/logout to persist the tech UUID
//   backgroundFetch — scheduled periodic job that reads the UUID and POSTs location

addEventListener('setTechId', async (resolve, _reject, args) => {
  try {
    const techId = args.detail?.techId ?? ''
    if (techId) {
      await CapacitorKV.set('tech_id', techId)
    } else {
      await CapacitorKV.remove('tech_id')
    }
  } catch (_) {}
  resolve()
})

addEventListener('backgroundFetch', async (resolve, _reject, _args) => {
  try {
    const { value: techId } = await CapacitorKV.get('tech_id')
    if (!techId) { resolve(); return }

    const pos = await Geolocation.getCurrentPosition({
      enableHighAccuracy: false,
      timeout: 10000,
    })

    await fetch(`https://lift-agent.com/webhooks/location/${techId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        latitude: pos.coords.latitude,
        longitude: pos.coords.longitude,
      }),
    })
  } catch (_) {}
  resolve()
})
