import { useEffect, useState } from 'react'
import { dashboardApi } from '../services/dashboardApi.js'
export default function FoundingJourneyGallery() {
  const [gallery, setGallery] = useState(null)
  useEffect(() => { dashboardApi.gallery().then((envelope) => setGallery(envelope.data)).catch(() => setGallery({ enabled: false, items: [] })) }, [])
  if (!gallery?.enabled) return <div className="emptyState"><b>LOCAL PRIVATE MEDIA</b><p>Gallery unavailable. No private media is published or copied into the application.</p></div>
  return <div className="galleryGrid">{gallery.items.map((item) => <figure key={item.id}><img src={item.image_url} alt={item.title} /><figcaption>{item.title}<small>LOCAL PRIVATE MEDIA</small></figcaption></figure>)}</div>
}
