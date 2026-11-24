import { Link } from 'react-router-dom'
import { Database, GitBranch, Share2, ShieldCheck } from 'lucide-react'

const capabilities = [
  {
    Icon: Database,
    title: 'Capture',
    desc: 'Kafka source connectors stream changes from operational databases (PostgreSQL, Db2) via CDC.',
  },
  {
    Icon: Share2,
    title: 'Transport',
    desc: 'Kafka brokers and topics carry the records, with contracts enforced in Schema Registry.',
  },
  {
    Icon: GitBranch,
    title: 'Transform',
    desc: 'Confluent Cloud for Flink builds golden records and business events as a star schema.',
  },
  {
    Icon: ShieldCheck,
    title: 'Serve & Govern',
    desc: 'Flink queries, sink connectors and Tableflow serve fresh context to apps, agents and Iceberg tables.',
  },
]

export default function HomePage() {
  return (
    <div className="home">
      <section className="home-hero">
        <span className="home-hero__eyebrow">Streamhouse on Confluent Cloud</span>
        <h1 className="home-hero__title">Customer 360 Streaming Demonstration</h1>
        <p className="home-hero__lede">
          A reference implementation of the{' '}
          <a href="https://streamhouse.com" target="_blank" rel="noopener noreferrer">
            Streamhouse architecture
          </a>{' '}
          on the Confluent Cloud stack — continuously capturing, governing and
          serving business facts so every application, agent and analytics
          consumer works from the same trusted, fresh context.
        </p>
        <figure className="home-hero__scene">
          <img
            src="/hero_streamhouse.svg"
            alt="Isometric view of the data flow: the transaction app and PostgreSQL feed Debezium CDC, Kafka topics and Flink, then the Iceberg data lake, the Lightning / RTCE serving layer queried by an AI agent, and a BI dashboard reading golden records."
          />
        </figure>
      </section>

      <section className="home-section">
        <h2 className="home-section__title">What this demo shows</h2>
        <p className="home-section__body">
          <strong>The goal: synchronize a change in business state everywhere it is used.</strong>{' '}
          Transactional microservices write customers, accounts and transactions to a
          SQL database. Change Data Capture streams those changes into Kafka, Flink
          enriches them into a Customer 360 profile, and the same golden records are
          served to this web app, to AI agents (via <strong>Flink snapshot queries, real-time context engine or Lightning tables</strong>), and to Iceberg tables in object
          storage — with no second set of copies or pipelines.
        </p>
      </section>

      <section className="home-section">
        <h2 className="home-section__title">Architecture on the Confluent stack</h2>
        <figure className="home-arch">
          <img
            src="/stream-cc-arch.drawio.png"
            alt="Streamhouse reference architecture mapped onto Confluent Cloud components: capture, transport, transform, serve and govern."
          />
          <figcaption>
            Capture → Transport → Transform → Serve, governed end-to-end by Schema
            Registry.
          </figcaption>
        </figure>
      </section>

      <section className="home-section">
        <h2 className="home-section__title">The four stages</h2>
        <div className="home-cards">
          {capabilities.map(({ Icon, title, desc }) => (
            <article key={title} className="home-card">
              <div className="home-card__icon">
                <Icon size={20} />
              </div>
              <h3 className="home-card__title">{title}</h3>
              <p className="home-card__desc">{desc}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="home-section">
        <h2 className="home-section__title">Explore the demo</h2>
        <div className="home-links">
          <Link className="btn" to="/analytics">Open the C360 Dashboard</Link>
          <Link className="btn btn--secondary" to="/data-products">View Data Products</Link>
          <Link className="btn btn--secondary" to="/customers">Browse Customers</Link>
          <Link className="btn btn--secondary" to="/chat">Ask the Assistant</Link>
        </div>
      </section>
    </div>
  )
}
