# ALTERNET — The Technical & Foundational Blueprint



Open-source architecture

Global network vision

Version 0.1 — Proposed



A decentralised, device-powered digital network that works with or without the conventional internet.

I would now treat Alternet as a serious infrastructure project, not a web application.

Your decisions establish three important foundations:

1. Open ownership: The software, protocols and specifications are open source. No company owns the network.
2. Universal access: People can use a browser, dedicated software, or their own servers. Browser users should have meaningful access without installing anything.
3. Global ambition: Alternet is designed to become an independent digital ecosystem, with its own addressing, services, communities and infrastructure.

There is one architectural principle I want to establish immediately:

> Alternet should not be a network that requires everybody to use Alternet's servers. It should be a network that helps independently operated computers and services find one another and communicate.

This distinction will determine almost every technical decision we make.

I would design it around a small, open network protocol and a collection of independently replaceable services.

# 1. The overall architecture

Let's call the architecture the Alternet Distributed Network Architecture (ADNA).

It consists of seven layers.

# The Alternet architecture

Conceptual architecture, from user-facing applications down to physical connectivity.

# 07

APPLICATIONS

Websites · Email · Forums · AI · Chat · Archives

# 06

SERVICE DISCOVERY

Find websites, people, servers, AI and communities

# 05

IDENTITY & TRUST

Cryptographic identities · Permissions · Reputation

# 04

STORAGE & REPLICATION

Personal storage · Shared storage · Content replication

# 03

NETWORK TRANSPORT

Direct connections · Relays · Synchronisation

# 02

PEER CONNECTIVITY

Peer discovery · Routing · Node management

# 01

PHYSICAL NETWORKS

Ethernet · Wi-Fi · Bluetooth · Internet · Radio

The critical architectural decision is that these layers must remain independent.

For example, someone should be able to replace their storage provider without changing their website, or replace their AI provider without changing their identity.

We should also avoid creating a new protocol for something that already has an excellent standard.

Alternet should connect existing technologies rather than unnecessarily reinvent them.

# 2. The node architecture

The node is the heart of Alternet.

Every computer running the software becomes a potential participant, whether it provides one service or twenty.

I'd create a modular application called Alternet Node.

[ITSWEBER Mesh - Self-hosted Homelab Dashboard](https://images.openai.com/static-rsc-4/ZGUfWnQBRZYqHlCppGURsKX4DXQJuezmsoUPbEYYl3oX6U0WBhUWlx05EjKPgtBNtb9rm6Bab085V8BBc0QXvnpq3GPJLMnCYBCnY1ZlD_CRffgYmTXpwwTIl1cG7s-Ie_gcEQNG_a_o6GlA71IhyJbNL_8IOkiZHbH7USX81F8?purpose=inline)

[itsweber.de](https://itsweber.de/itsweber-mesh?utm_source=chatgpt.com)

## Node components

| Component          | Responsibility                           |
| ------------------ | ---------------------------------------- |
| Node Core          | Starts and manages the node              |
| Peer Manager       | Discovers other nodes                    |
| Transport Engine   | Establishes network connections          |
| Identity Manager   | Manages cryptographic identity           |
| Service Registry   | Advertises available services            |
| Storage Engine     | Manages local and shared storage         |
| Replication Engine | Synchronises authorised data             |
| Web Gateway        | Publishes websites                       |
| Mail Connector     | Connects email infrastructure            |
| AI Connector       | Exposes local AI services                |
| Security Manager   | Enforces permissions and resource limits |
| Admin Interface    | Provides a simple user dashboard         |

Each component should be replaceable through a documented interface.

For instance, a developer could create an alternative storage engine without rewriting the node software.

## Node operating modes

I'd support four modes.

Personal Node

For ordinary people using laptops and desktops.

Full Node

For servers, NAS devices and home labs.

Relay / Gateway Node

For nodes providing connectivity to other participants.

Community Node

For libraries, universities, clubs and local organisations.

A node can switch between these modes and combine their capabilities.

A personal computer shouldn't need to run continuously to participate. When it goes offline, its services become unavailable unless replicated elsewhere.

# 3. Connectivity and the actual network protocols

This is where we need to be disciplined. We should choose proven technologies and build a coherent system around them.

## Recommended protocol stack

| Function                   | Recommended technology                                   | Decision                   |
| -------------------------- | -------------------------------------------------------- | -------------------------- |
| Peer-to-peer networking    | libp2p                                                   | Core                       |
| Direct encrypted transport | QUIC / TLS 1.3                                           | Core                       |
| Browser peer connections   | WebRTC DataChannels                                      | Core                       |
| Local discovery            | mDNS / DNS-SD                                            | Core                       |
| Peer routing               | Kademlia DHT                                             | Core                       |
| Content addressing         | CID-style content identifiers                            | Core                       |
| Content storage            | IPFS-compatible mechanisms, with optional alternatives   | Core interface             |
| Community federation       | ActivityPub or compatible federation adapters            | Optional interoperability  |
| Messaging                  | Matrix-compatible integration or native service protocol | Interoperability           |
| Email                      | SMTP / IMAP / standard DNS                               | Native service integration |
| AI services                | HTTP APIs, OpenAI-compatible interfaces, MCP adapters    | Native service integration |

I particularly favour libp2p because it already supports multiple transports, browser and server environments, encryption, relays and NAT traversal. This means we don't need to invent the underlying networking machinery.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://libp2p.io\&sz=32)

libp2p+2



### A. How a connection actually happens

Suppose Alice is running Alternet on her laptop and Bob is running it on his home server.

The connection sequence should be:

1. Discovery

   Alice's node discovers Bob locally or through the network directory/DHT.
2. Identity verification

   Alice checks Bob's cryptographic node identity.
3. Connection negotiation

   The nodes try an appropriate direct transport.
4. NAT traversal

   If necessary, they attempt hole punching, with a relay as fallback.
5. Permission negotiation

   Bob decides which services Alice can access.
6. Service connection

   Alice can now access Bob's authorised website, files, email gateway or AI endpoint.

This is not theoretical networking. The libp2p documentation describes the use of relays, automatic address detection and hole punching to connect devices behind NATs.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://libp2p.io\&sz=32)

libp2p+1



### B. A realistic connectivity hierarchy

I'd implement connection attempts in this order:

1. Local Ethernet or Wi-Fi.
2. Direct local wireless connections where supported.
3. Direct internet connection.
4. NAT traversal.
5. Encrypted relay.
6. Store-and-forward when neither endpoint is currently reachable.

This last option is important.

If two computers cannot communicate simultaneously, they can sometimes exchange queued messages or replicated content through an intermediary when they reconnect.

It is not the same as a live connection, but it makes the network more resilient.

### C. Browser versus installed software

We need to be honest about the distinction.

A normal browser cannot simply become a full networking node with unrestricted access to Wi-Fi hardware, raw sockets and background processing.

I would therefore support two experiences:

- Alternet Web: Browse, publish, communicate and use accessible services through browser-compatible gateways.
- Alternet Connect: Full node capabilities, local discovery, storage contribution, relaying, direct connections and background synchronisation where the operating system permits it.

WebRTC provides standard browser-to-browser data channels, while installed software can use the broader libp2p transport capabilities.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://www.rfc-editor.org\&sz=32)

RFC Editor+1



This gives us broad accessibility without pretending that every browser has the same capabilities as a full node.

# 4. Identity, addressing and ownership

I would make this one of the most carefully designed parts of the project.

We need to distinguish four identities:

- A person.
- A computer or node.
- A service.
- A digital space, such as a website or community.

They should not be permanently tied together.

For example:

A person can own three computers, operate two websites and participate in five communities.

If their laptop breaks, their identity and websites should not disappear.

## The Alternet identity model

Every node receives a cryptographic identity.

Every person can optionally have a persistent identity.

Every service receives a separately verifiable identity or ownership binding.

We should use established cryptographic libraries and algorithms, not invent our own cryptography.

### Addressing

I would establish two addressing systems.

1\. Human-readable names

For example:

```
alice.alternet
radio.alternet
history.alternet
ai.alternet
```

These are human-friendly names resolved through Alternet's naming system.

2\. Cryptographic identifiers

Every node and service has an immutable identifier derived from its public key or content identity.

For example:

```
node://<cryptographic-node-id>
service://<service-id>
content://<content-id>
```

These are conceptual URI schemes, not final standards.

The benefit is that a person can change their human-readable address without changing their underlying cryptographic identity.

### Naming must not become a central point of control

I would use a combination of:

- Signed naming records.
- Multiple independent directory providers.
- DHT-based discovery.
- Optional self-hosted naming authorities.
- Human-readable aliases.
- Conflict detection and resolution.

A global directory would be a convenience, not the only way to find things.

There is also a distinction between a human-readable name and a conventional DNS domain. A `.alternet` name won't automatically resolve in ordinary browsers without a compatible browser, local resolver, or gateway. We need to design this deliberately.

# 5. Storage, replication and the shared infrastructure

This is where your original idea of dedicating spare disk space becomes a real infrastructure feature.

I would create a subsystem called Alternet Storage Network (ASN).

Its purpose is to allow participants to contribute storage, consume storage, replicate content and host services without depending on one central hosting provider.

## A. Three storage categories

| Category       | Ownership                   | Replication                     |
| -------------- | --------------------------- | ------------------------------- |
| Personal       | Individual owner            | Only with permission            |
| Community      | Community or organisation   | According to community policy   |
| Public archive | Published for public access | Eligible for public replication |

A node operator should be able to select exactly which category they support.

## B. How replication works

I would borrow the useful concepts of content addressing and pinning from IPFS, but build an Alternet storage interface that isn't tied to one storage implementation.

IPFS uses content identifiers and explicit pinning to protect content from garbage collection. This is useful because simply uploading something to a distributed network does not guarantee that it will remain available.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://docs.ipfs.tech\&sz=32)

IPFS Docs+2



An example:

1. Alice publishes a website.
2. The website is divided into content-addressed objects.
3. Alice requests two additional storage copies.
4. Two participating nodes accept the replication request.
5. The objects are verified using their content hashes.
6. The network records which nodes have agreed to retain them.
7. If Alice's computer goes offline, the other nodes can continue serving the website.

Example: distributed website hosting

Alice's computer

Original website · 1 GB

Node B

Replica 1

Node C

Replica 2

All replicas are verified against the original content identifier.

The storage engine should have:

- Content addressing.
- Integrity verification.
- Optional encryption.
- Replication policies.
- Storage quotas.
- Retention agreements.
- Availability monitoring.
- Garbage collection.
- Explicit deletion and unpinning mechanisms.

Important: Replication does not mean automatic copying of everything. It must be opt-in, with clear retention periods and deletion rules. Private content should use encryption and authorised access controls.

## C. Storage contribution marketplace — without necessarily having money

I'd create a directory of storage providers.

A node could advertise:

```
Provider: Alice's Home Server
Available: 2 TB
Location: United Kingdom
Retention: 24/7
Storage type: Public content
Replication: Supported
Cost: Free
```

Another provider might advertise 100 GB but only be available overnight.

Initially, this is a voluntary contribution system, not a financial marketplace.

Later, we could add reputation, service agreements and optional compensation without making payment mandatory to participate.

## D. Your own infrastructure

I'd establish an initial Alternet infrastructure cluster.

For example:

- A central bootstrap and discovery service.
- A few independent relay servers.
- A modest distributed storage pool.
- A global directory service.
- A public web gateway.
- Developer documentation and software repositories.

But these services must be replaceable by community-operated alternatives.

The initial infrastructure helps the network get started. It should not become a permanent dependency.

# 6. Websites, domains and independent services

We need a proper service architecture, not just a storage system.

I'd establish an Alternet Service Protocol (ASP).

ASP is a proposed application-level interface for advertising and discovering services.

It would not replace HTTP, SMTP, IMAP or other established protocols.

Instead, it tells the network:

- What a service is.
- Who operates it.
- Where it can be reached.
- What protocol it speaks.
- What permissions it requires.
- Whether it is currently available.
- Whether it supports offline access.

## Example service announcement

An independently operated web server might publish a signed service record like this:

```
{
  "service_type": "website",
  "name": "Alice's Digital Workshop",
  "owner": "alice-public-key",
  "node": "node-public-key",
  "protocol": "https",
  "capabilities": [
    "html",
    "static-files",
    "web-applications"
  ],
  "access": "public",
  "availability": "best-effort"
}
```

This is an illustrative schema, not a final protocol specification.

A user searching for independent websites could discover Alice's site without knowing where her computer is physically located.

## Hosting options

I'd support four distinct approaches:

| Hosting model    | How it works                                          |
| ---------------- | ----------------------------------------------------- |
| Self-hosted      | Website runs on the owner's computer                  |
| Community-hosted | A local community server hosts it                     |
| Shared-hosted    | Your infrastructure provides free hosting             |
| Distributed      | Multiple authorised nodes replicate and serve content |

All four should be equally legitimate.

## Existing websites must be welcome

Someone with a website on an existing domain should be able to register its Alternet presence.

For example:

`myproject.com`

Could also be discovered through:

`myproject.alternet`

The Alternet address would be an alias or discovery entry, not necessarily a replacement for their real domain.

For the first version, we could provide an HTTPS gateway for human-readable Alternet addresses. Later, dedicated local DNS resolvers and browser integrations could provide more seamless access.

# 7. Email architecture

Email is an independent service and should remain interoperable with the wider internet.

I would create an Alternet Mail Connector, not an entirely new email system.

It would support:

| Function                    | Standard              |
| --------------------------- | --------------------- |
| Sending email               | SMTP                  |
| Receiving and reading email | IMAP4rev2             |
| Domain routing              | DNS MX                |
| Sender authentication       | SPF, DKIM and DMARC   |
| Local offline mail          | Encrypted local queue |

SMTP and IMAP already provide the basic interoperability we need. IMAP4rev2 also defines mechanisms for offline client synchronisation.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://www.rfc-editor.org\&sz=32)

RFC Editor+1



There are two operating modes:

Alternet-only mail

People communicate within the network, including across disconnected local nodes. Messages queue until recipients are reachable.

Conventional internet mail

People send and receive messages using normal email addresses.

For the latter, a node needs a reachable mail service and appropriate domain and deliverability configuration. A laptop behind a residential NAT cannot automatically become a reliable global email server.

I would offer optional shared outbound mail relays, while allowing technically advanced users to run their own mail infrastructure.

# 8. The AI and LLM layer

I would give AI a first-class place in Alternet.

Not because every person needs an AI assistant, but because people running their own models could provide useful infrastructure to everyone else.

Call this subsystem Alternet Intelligence Network (AIN).

## AI services people can publish

- Local language models.
- Embedding services.
- Vector databases.
- Image-generation systems.
- Speech-to-text.
- Text-to-speech.
- Coding assistants.
- Personal AI agents.
- Search and research agents.
- MCP-compatible tools.

[온프레미스 환경에서 Ollama + Open WebUI로 사내 LLM 구축하기](https://images.openai.com/static-rsc-4/cCuKNWNQLsKnqA6LM4jXSGBQhH07J4_5XpWgMsuLqJAKSw8IaixQUUzb_hwvXnzV89YdY1gJboZZX-kXsRVx8NsUQhrdOk099albfLufK2EMaqYtxpXT9_wbuwNnsbTrs5yI2XgTpFnwD0lLTcqM26V98UI87zd8qDqP7Zsvg30?purpose=inline)

[somaz.tistory.com](https://somaz.tistory.com/488?utm_source=chatgpt.com)

### How it would work

Imagine Bob is running Ollama on his computer.

He installs Alternet Node and enables the AI connector.

The connector discovers his local inference endpoint and asks him which capabilities he wants to expose.

He selects:

- Model: locally installed model.
- Access: selected community.
- Maximum simultaneous requests: 2.
- Daily resource allowance: configured by Bob.
- Data policy: no persistent request logging.

The network then publishes a service announcement.

Alice can discover Bob's AI service and use it through an authorised API.

We should initially support OpenAI-compatible APIs and Ollama, with adapters for other inference platforms.

### The really interesting possibility: distributed AI communities

A community could operate several AI services across different nodes.

For example:

- One machine provides inference.
- Another provides embeddings.
- Another stores the community knowledge base.
- Another operates the web interface.

A community could build its own AI environment without buying a cloud AI subscription.

But I would not initially try to split a single model's inference across random household computers. That introduces substantial latency, networking and hardware compatibility problems.

Start with independent AI providers and orchestration across services.

Also, AI agents must never receive unrestricted access to participating nodes. Each tool invocation needs explicit permissions, resource limits and auditability.

# 9. Community communication and federation

For social communication, I would avoid reinventing everything.

ActivityPub already provides standardised client-to-server and server-to-server federation for decentralised social services.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://www.w3.org\&sz=32)

W3C



Matrix offers another useful model for federated communication between independently operated servers, including message delivery and room history.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://spec.matrix.org\&sz=32)

Matrix Specification+1



I would support both through adapters.

The native Alternet environment could provide:

- Discussion boards.
- Private messaging.
- Live chat.
- Community announcements.
- Public guestbooks.
- Forums.
- Events.
- Digital clubs.
- Independent community websites.

However, the key principle is that communities can use their own software and servers.

Alternet should not force every group to use a single central forum implementation.

# 10. Security and trust architecture

This is not something we can bolt on later.

When you allow strangers to contribute storage, run servers, provide AI services and relay traffic, you are creating a network with a significant security responsibility.

I would establish the following rules from the beginning.

## A. Every node has a cryptographic identity

Each node gets:

- A public/private key pair.
- A unique node identifier.
- Signed service announcements.
- A mechanism for key rotation.
- A way to revoke compromised identities.

People should be able to back up their identities and recover them on new machines.

## B. Trust is not the same as identity

A node proving that it is genuinely Alice's computer doesn't mean Alice is trustworthy.

We need separate trust relationships.

For example:

| Trust level       | Meaning                          |
| ----------------- | -------------------------------- |
| Unknown           | No previous relationship         |
| Identified        | Cryptographic identity verified  |
| Known             | Explicitly trusted by the user   |
| Community trusted | Accepted under community policy  |
| Restricted        | Limited capabilities             |
| Blocked           | No connections or service access |

Trust should be contextual. A node may be trusted to serve public images but not to store private email.

## C. Never expose a computer by default

This is crucial.

Installing Alternet must not automatically:

- Expose local files.
- Open arbitrary network ports.
- Publish a computer's services.
- Allow strangers to use its CPU.
- Allow strangers to use its GPU.
- Make personal storage available.

Every contribution must be deliberately enabled.

## D. Sandboxing

Third-party applications should run inside isolated environments.

I would investigate:

- Containers.
- WebAssembly (WASM).
- OS-native sandboxing.
- Restricted filesystem access.
- Network permission controls.
- CPU, memory and bandwidth limits.

A community website should not be able to access the host computer's private files.

## E. Abuse prevention

A decentralised network needs practical ways to handle:

- Malware distribution.
- Spam.
- Phishing.
- Illegal content.
- Storage abuse.
- Denial-of-service attacks.
- Malicious AI agents.
- Impersonation.

Each community should control its own membership and moderation, while individual node operators retain the ability to refuse services and block peers.

The network should support signed abuse reports, transparent blocklists, rate limits and independently maintained trust policies.

No central authority should be able to silently delete content everywhere, but neither should the protocol force an operator to host content they reject.

# 11. Governance: how an open Alternet should be organised

You selected open ownership. I agree.

But open source alone does not guarantee decentralised governance.

We need to ensure that no individual, company or foundation can quietly turn Alternet into a closed commercial platform.

I would propose a three-part structure.

Alternet Foundation

Stewardship · Legal affairs · Trademark · Infrastructure grants

Technical Council

Protocol standards and releases

Community Assembly

Users, operators and developers

Three independent governance functions, with published decisions and transparent processes.

### The Foundation

Its job would be to:

- Protect the open-source mission.
- Manage project funds.
- Support development.
- Maintain public infrastructure.
- Administer trademarks.
- Provide legal and organisational continuity.

It should not own the data or services operated by the network.

### The Technical Council

Responsible for:

- Protocol specifications.
- Compatibility standards.
- Security reviews.
- Reference implementations.
- Release management.
- Deprecation policies.

Changes should be proposed publicly, reviewed and documented.

### The Community Assembly

Includes:

- Individual users.
- Server operators.
- Developers.
- Community moderators.
- Storage contributors.
- AI service providers.

Its job is to provide input on the direction of the network and elect representatives to appropriate governance roles.

### Open-source licensing

My suggested starting point:

| Asset                   | Proposed licence                  |
| ----------------------- | --------------------------------- |
| Node software           | Apache 2.0                        |
| Client software         | Apache 2.0                        |
| Protocol specifications | CC0 or similarly permissive terms |
| Documentation           | CC BY 4.0                         |
| SDKs                    | Apache 2.0                        |

Apache 2.0 is a useful option because it allows commercial use, modification and redistribution while including an express patent licence.

I'd keep the protocol specifications free of proprietary extensions that are necessary for compatibility.

The Alternet name and logo could be protected through a community-governed trademark policy without restricting independent compatible implementations.

# 12. Technical implementation: what should we actually build with?

Now we can get specific.

I would favour a relatively small number of technologies, rather than building an enormous collection of microservices.

## Proposed development stack

[Tudo que você precisa saber antes de começar a programar em GO - Canaltech](https://images.openai.com/static-rsc-4/Nd8EkqZOhItHptx8z7e2MqlVVEhgfR1XapG_ErYn8fgUijRUWFjCDLldGw08C_p0zSAUI50MUsM-M5tmLs-lTCXTVa3mmdf9G1ArGZU917Z7fybPHTbOcl8hsHigFTvoyIf87M5XP9cSVgqSfSW_5ZQC1dUC7lMjsfZXFdsfPNA?purpose=inline)

Go — Node Core

Cross-platform networking, service management and node operations

Preferred

[TypeScript Logo Icons for Web and App Development](https://images.openai.com/static-rsc-4/Pbx8y0BkFx2FGL0rrQv12qhf7VCxQjJIxX5qzDbXfFc_2r0281FTrrhYxXs3oeHVXGVOioNH7bLrVixEVSASmJ_wcEhF77ZXSHxlzycjvcxjtXJBHHMnjUNYoQ5lFVUZW7gTZd7KpLmODFhOjJ9wCXSRFqfHbE7Oj1PItTwTFWk?purpose=inline)

TypeScript — Web and desktop interfaces

Browser client, admin dashboard and developer SDKs

[Building a cross platform Rust CI/CD pipeline with GitHub Actions](https://images.openai.com/static-rsc-4/AIBv059WEUbUQJJxX5ILTs3wLPBOexEPkq12X3rnJVCz1eIfqPv5RGBKMJpBeqo2114TUE1XKqSk0_7AdyS6Blj7aWXxQiWHjYypGEmZTSBw8wvpEwji9k8kUvworAhMgY_SCXFUxg3_xJb8gIqgJ7ED9Yhyu_AA2vinS71MhOE?purpose=inline)

Rust — Optional specialised components

Performance-sensitive components and security-critical services

[SQLite Logo .PNG and .AI, .EPS, .CDR, .PDF, .SVG - iconLogoVector](https://images.openai.com/static-rsc-4/RPKvjxxl5sxbe_zRYWlc7SmLXTErfN6rIx88GJl53nRU32x6e5RG0rtZpxjsv1dwIu4epD8nCDYwAiB9e3kw3RmB1_NiGQEYhH2uBZFxUwovZePmm1VVZ66hk6Q0LL0HH3RI5r0j5_KS1rLXKI6tunUZmg0BmVGZaHbB1L3NsXA?purpose=inline)

SQLite — Local state

Embedded databases for individual nodes

[Postgresql Logo PNG Transparent With Clear Background ID 473068 |  TOPpng](https://images.openai.com/static-rsc-4/x6sDZ8oKI9URixQ5E82vqCQV1aR38qK7E8n0HKggx6_cD8G7QtlPuHlyO99GalHPJOycjs41bPgfrRTqdHFqayPWJl57hxNttQynREzHXSUSsui_zVAB_ssyc1xdm_msJ5GiDzf23C9Z2RuuoyVCc6J0AbuAqX5Aul_x1J78q2I?purpose=inline)

PostgreSQL — Larger services

Directories, community applications and shared infrastructure

[Exploring Linux: Its Revolutionary Journey and Modern Impact](https://images.openai.com/static-rsc-4/x88QgS8BGro4jmnX5nYt0qakZVD-GC-oflhDXEoS9NOyUBpf0fe0IL2YiliMsX5IfwkJGpMcha6jdTQ_xX1cx__upFWOeU5L1WNY1cmTbebPX1rLQGaXxntYbamos-GqMnR0LInDC_U3tXNWvdL1oKeGgugj4CMBVnIB_p8Bc7E?purpose=inline)

Linux / Windows / macOS

Initial desktop and server platforms

Why Go first?

Because I would rather have a working network in six months than spend a year developing a theoretically perfect networking engine.

Go has a mature libp2p implementation and is well suited to a portable background service.

Rust remains a strong option where we need more control over memory safety and low-level performance.

For the first release, I'd build a modular monolith rather than microservices. The components can communicate through clean internal interfaces, but we don't need to deploy 15 separate services just to connect two computers.

## Proposed repository structure

```
alternet/
│
├── core/
│   ├── identity/
│   ├── peers/
│   ├── transport/
│   ├── discovery/
│   ├── security/
│   └── service-registry/
│
├── storage/
│   ├── local/
│   ├── content-addressing/
│   ├── replication/
│   └── providers/
│
├── services/
│   ├── web/
│   ├── mail/
│   ├── messaging/
│   ├── ai/
│   └── archive/
│
├── clients/
│   ├── web/
│   ├── desktop/
│   └── mobile/
│
├── gateway/
│   ├── http/
│   ├── dns/
│   └── browser/
│
├── sdk/
│   ├── go/
│   ├── typescript/
│   └── python/
│
├── specifications/
│   ├── identity/
│   ├── discovery/
│   ├── services/
│   ├── storage/
│   └── federation/
│
└── infrastructure/
    ├── bootstrap/
    ├── relays/
    ├── directory/
    └── monitoring/
```

This is a proposed repository structure, not an existing implementation.

# 13. The implementation roadmap

I would build this in ten milestones, with working software at every stage.

The most important thing: do not try to build the entire global Alternet before demonstrating that two computers can form a useful independent network.

# Alternet development roadmap

Indicative schedule for a small, experienced development team. These are estimates, not delivery commitments.

1. Foundation and specifications

   Months 1–2
   - Define network identity.
   - Define node protocol.
   - Choose initial transport.
   - Establish security model.
   - Publish architecture and open-source repository.
   - Create initial reference implementation.
2. Two-node networking

   Months 2–3
   - Install on Windows and Linux.
   - Discover peers on local Wi-Fi.
   - Establish encrypted connections.
   - Exchange messages.
   - Work without internet.
3. Global peer connectivity

   Months 3–4
   - Introduce bootstrap peers.
   - Implement DHT discovery.
   - Introduce relay infrastructure.
   - Test NAT traversal.
   - Test different networks and ISPs.
4. Service discovery and websites

   Months 4–5
   - Publish service records.
   - Host existing HTML websites.
   - Introduce browser gateway.
   - Create human-readable addresses.
   - Discover independent websites.
5. Storage and replication

   Months 5–7
   - Add storage providers.
   - Introduce content addressing.
   - Add replication policies.
   - Verify integrity.
   - Test offline website availability.
6. Community and messaging

   Months 7–8
   - Native messaging.
   - Community spaces.
   - ActivityPub interoperability.
   - Optional Matrix integration.
   - Offline message queues.
7. AI ecosystem

   Months 8–9
   - Ollama integration.
   - OpenAI-compatible endpoints.
   - AI service directory.
   - Provider permissions.
   - Resource allocation.
8. Email and advanced hosting

   Months 9–10
   - SMTP and IMAP integration.
   - Existing domain support.
   - Shared mail relay.
   - Independent web applications.
9. Community infrastructure

   Months 10–11
   - Raspberry Pi installation.
   - Community server package.
   - Self-hosting documentation.
   - Storage contribution system.
   - Node operator tools.
10. Public beta

    Months 11–12
    - Public developer preview.
    - Independent node operators.
    - Security audit.
    - Interoperability testing.
    - Public protocol documentation.

The schedule assumes a focused team of approximately four to six experienced developers, plus security and infrastructure support. A solo developer should treat this as a multi-year project and concentrate on the first few milestones.

## The first three demonstrations we must achieve

I would make these the project's initial proof points.

Proof 01

The disconnected network

Two laptops, no internet, local Wi-Fi, independent websites and messaging.

[Zwei Computer miteinander verbinden: So geht's! - CHIP](https://images.openai.com/static-rsc-4/PY4X9t6SYdTTTM7Giz7FwpVrqNzkoW6z_h0M3m9hiYnvxS-VwOipdsexdqVMPMdcFCrMT_Zmw_VxpgHYYGnGWNuDm4mMCnR6lkTH_hnWJYcDJGtr1-kiM8mutcaKUiabFz4JzwLcj5pzJdw1zwe_V_g4VPh3PXz7xKyA9zcC-kA?purpose=inline)

[chip.de](https://www.chip.de/video/Zwei-Computer-miteinander-verbinden-So-geht-s-Video_182539362.html?utm_source=chatgpt.com)

Proof 02

The global network

Two computers in different countries, connected through independent internet connections, discovering and accessing each other's services.

[Cos'è una rete mesh e come funziona - FASTWEBPLUS](https://images.openai.com/static-rsc-4/psxvRJ6AZQzRmxs4n77Oj3KK5fSy6CK6ZOymwr8pf1573hjGe8xKX8u0lfAjdJJovLdIVc8z3R78GejV4mDj27_JPisR0PkexMADVt2Jx-WSZu_zX7kKio_zfy9KV2_C5F42AMfRkaRQzE7DMulyuHmyKKoRWmUdmwYyYdQLjyU?purpose=inline)

[fastweb.it](https://www.fastweb.it/fastweb-plus/digital-magazine/cos-e-una-rete-mesh-e-come-funziona/?utm_source=chatgpt.com)

Proof 03

The distributed infrastructure

A website remains accessible from another node when its original host goes offline, with authorised replication.

[💾 Virtualization Storage in 2026: NVMe, SAN, Ceph, vSAN, NFS or iSCSI](https://images.openai.com/static-rsc-4/JbYnvL1ovqM1RHSBGK6AJdDql6Rd6vEKw7jSIBrgJJcS5Co9-axWAfJ43kCVkapFVHr4qQpDtt18us07dkMXkcHCGBBq_RHWqAISKtHre0MqTrJg9k5v6sAAKRGAz2b1LhKWnGlpQA0LambzjxvXDvo6Z6U95p37iwlhpuHCjbE?purpose=inline)

[servermall.com](https://servermall.com/blog/how-to-choose-storage-for-virtualization-local-nvme-san-ceph-vsan-nfs-or-iscsi/?utm_source=chatgpt.com)

If we achieve these three demonstrations, we will have validated the fundamental proposition of Alternet.

# 14. How we fund and sustain the network

This needs to be addressed early because you want people to publish and participate for free.

There is no such thing as unlimited free storage or unlimited free bandwidth. Someone pays the electricity, hardware, connectivity and maintenance costs.

I would establish a shared infrastructure model.

| Resource           | Initial provider            | Long-term model                      |
| ------------------ | --------------------------- | ------------------------------------ |
| Bootstrap services | Foundation                  | Multiple independent operators       |
| Relay capacity     | Foundation                  | Community-contributed                |
| Website storage    | Your initial allocation     | Distributed contributors             |
| AI inference       | Independent providers       | Voluntary and optional paid services |
| Email              | Foundation and self-hosters | Independent mail operators           |
| Local connectivity | Community nodes             | Libraries, homes and organisations   |

Your proposed disk allocation could become the first public storage pool.

I would start with a modest allocation rather than immediately promising enormous amounts of free storage.

For example, the initial programme could offer:

- Free static website hosting.
- A small personal storage allowance.
- Free community discussion spaces.
- Free access to participating public AI services.
- Optional additional storage through contributors.

The important distinction is that the network itself is free to participate in, while infrastructure resources have transparent limits.

## A potential growth loop

Someone joins Alternet

They create or connect a service

Website · AI · Storage · Email · Community

Other people discover it

They join and contribute

The network becomes more useful as it grows

This is the viral mechanism I'd focus on: every new participant can bring something useful to the network, rather than merely adding another account.

# 15. Five architectural decisions I would protect

Before development begins, I want to highlight five things that could make or break the project.

1\. Never make the global directory mandatory.

A person should be able to connect to a known node directly, even if the main discovery infrastructure disappears.

2\. Never make the network dependent on one storage provider.

Your infrastructure can be the first provider, but it must be replaceable.

3\. Never assume every node is permanently online.

Laptops sleep. Computers shut down. People travel. Phones restrict background activity.

The network needs graceful disconnection, queues, synchronisation and optional replication.

4\. Never automatically trust contributed resources.

Storage, AI inference, relays and hosted applications all require separate permissions and security boundaries.

5\. Never make compatibility an afterthought.

We should support ordinary web technologies, conventional email, established networking standards and existing AI infrastructure.

A successful Alternet should complement the existing internet while creating an independent alternative.

# 16. The documents we need to create

I would organise the project around six foundational documents.

| Document                     | Purpose                              |
| ---------------------------- | ------------------------------------ |
| 001 — Alternet Manifesto     | Mission, principles and ownership    |
| 002 — Network Architecture   | Overall technical design             |
| 003 — Node Specification     | How nodes operate                    |
| 004 — Protocol Specification | How machines communicate             |
| 005 — Security & Governance  | Trust, privacy and administration    |
| 006 — Developer Roadmap      | Implementation, testing and releases |

These should become public documents in the project's Git repository.

For technical reference, I'd use:

- [libp2p](https://libp2p.io/?utm_source=chatgpt.com) — networking architecture.
- [libp2p hole punching](https://libp2p.io/docs/hole-punching/?utm_source=chatgpt.com) — direct connections through NAT.
- [IPFS documentation](https://docs.ipfs.tech/?utm_source=chatgpt.com) — content addressing and storage.
- [W3C ActivityPub](https://www.w3.org/TR/activitypub/?utm_source=chatgpt.com) — social federation.
- [Matrix federation specification](https://spec.matrix.org/latest/server-server-api/?utm_source=chatgpt.com) — federated messaging.
- [SMTP specification](https://www.rfc-editor.org/rfc/rfc5321.html?utm_source=chatgpt.com) and [IMAP specification](https://www.rfc-editor.org/rfc/rfc9051.html?utm_source=chatgpt.com) — email interoperability.

These are building blocks, not dependencies that must all be adopted. We should evaluate their licences, implementation maturity, security and compatibility before selecting final versions.

# 17. My recommended immediate starting point

I would not start by building the website or even the user interface.

I'd start by creating a working Alternet Node Core.

# ALTERNET CORE 0.1

First development target

The first release must demonstrate:

- Cross-platform node installation.
- Cryptographic node identities.
- Automatic local peer discovery.
- Encrypted peer-to-peer connections.
- Internet-based peer connectivity.
- Relay fallback.
- Signed service announcements.
- A basic website service.
- A basic content replication mechanism.
- Offline operation and resynchronisation.

First practical experiment

Computer A

Runs an Alternet node and hosts a website.

Computer B

Discovers Computer A and accesses its website.

Disconnect the internet

Both machines continue communicating locally.

Reconnect

Nodes synchronise authorised changes.

## One additional recommendation: make the protocol the product

I would publish the protocol specification before the first production release.

This means another developer could build an Alternet-compatible node without using our software.

That is how we avoid becoming another platform that claims to be decentralised but ultimately controls the network through its own implementation.

# 18. Let's turn this into a real project

There is one final decision I'd like to make before moving into actual source code and repository creation.

We have three possible approaches to the initial development.

1\. What should we produce first?

The actual network core: node software, discovery, connectivity and replication.

A complete technical specification and protocol documentation before coding.

A working prototype with two computers connecting and sharing websites.

2\. What development model are you considering?

Start small, with me developing the project and using AI assistance.

Start an open-source developer community immediately.

Build a small dedicated development team.

Build the prototype first, then open it to contributors.

3\. Working project name

Alternet

Alternet Network

Keep Alternet as a codename until branding is finalised.

Start the actual project&#x20;

My personal recommendation is to build the prototype first, but write the protocol specification alongside it.

I would especially like to see two ordinary computers connect without internet, publish and discover websites, and replicate content. Then connect the same computers across the internet.

That is the moment Alternet stops being an idea and becomes a functioning network.

And I would keep one principle at the centre of everything:

The internet connects computers. Alternet should enable computers, people and their independently created digital worlds to become part of something bigger, without giving up ownership or control.