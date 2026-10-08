export default function PageHeader({ eyebrow = 'AIOS', title, description, actions }) {
  return <header className="pageHeader"><div><p>{eyebrow}</p><h1 tabIndex="-1">{title}</h1>{description && <span>{description}</span>}</div>{actions && <div className="pageActions">{actions}</div>}</header>
}
