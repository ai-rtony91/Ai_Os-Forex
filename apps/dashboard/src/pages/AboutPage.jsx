import GlassPanel from '../components/GlassPanel.jsx'
import FoundingJourneyGallery from '../components/FoundingJourneyGallery.jsx'
import MotivationVehicleCard from '../components/MotivationVehicleCard.jsx'
import PageHeader from '../components/PageHeader.jsx'
export default function AboutPage() { return <><PageHeader title="About AIOS" description="The purpose, human-control model, founding journey, and performance motivation behind AIOS." />
  <div className="aboutGrid"><GlassPanel family="market"><small>01 · AIOS PURPOSE</small><h2>Governed intelligence for consequential work</h2><p>AIOS is a governed, human-controlled, AI-assisted trading and project operating environment. It organizes evidence, validation, and bounded action without claiming autonomous authority over money.</p></GlassPanel><GlassPanel family="performance"><small>03 · HUMAN-CONTROLLED DESIGN</small><h2>Review before release</h2><p>Human approval, data provenance, risk controls, broker separation, protected credentials, validation, and review remain explicit system boundaries.</p></GlassPanel></div>
  <GlassPanel family="research"><small>02 · FOUNDING JOURNEY</small><h2>Private local gallery</h2><p>Approved local manifest titles only. Media remains loopback-only, uncropped, unmodified, and outside tracked application assets.</p><FoundingJourneyGallery /></GlassPanel>
  <GlassPanel family="neutral"><small>04 · PERFORMANCE MOTIVATION</small><MotivationVehicleCard /></GlassPanel>
  <GlassPanel family="neutral"><small>05 · ATTRIBUTIONS</small><h2>Third-party registry</h2><a className="textLink" href="/THIRD_PARTY_ATTRIBUTIONS.md" target="_blank" rel="noreferrer">Open THIRD_PARTY_ATTRIBUTIONS.md</a></GlassPanel></> }
