# Edu-Voice-AI — Real Integration Checklist

**Owner:** Yasin (Voice Gateway + DevOps + Infrastructure)  
**Status:** Pre-Integration Validation Active  
**Rule:** Checkboxes are only marked complete when confirmed evidence exists in the repository.  

---

## PHASE A — Aravind Integration (Supabase / Tenant Routing)
*Owner: Aravind*

- [ ] Contract received
- [ ] Schema verified
- [ ] Authentication verified
- [ ] Resolver adapter designed
- [ ] Tenant isolation verified
- [ ] Tests prepared
- [ ] Integration approved

---

## PHASE B — Lokesh Integration (Voice Engine / Conversational AI)
*Owner: Lokesh*

- [ ] Contract received
- [ ] Transport verified
- [ ] Audio format verified
- [ ] Event schema verified
- [ ] Barge-in behavior verified
- [ ] Error handling verified
- [ ] Tests prepared
- [ ] Integration approved

---

## PHASE C — Exotel Carrier Integration (Telecom Carrier)
*Owner: Lokesh (Exotel integration owned by Lokesh / Outside Yasin Scope)*

- [ ] Exotel adapter delivered by Lokesh (implementing `BaseTelephonyProvider`)
- [ ] Webhook verified
- [ ] Signature verified
- [ ] WebSocket streaming verified
- [ ] Media format verified
- [ ] Codec verified
- [ ] Call transfer API verified
- [ ] Tests prepared
- [ ] Integration approved

---

## PHASE D — AWS (Cloud Infrastructure & Deployment)
*Owner: Yasin*

- [ ] Region confirmed
- [ ] ECR confirmed
- [ ] ECS confirmed
- [ ] ALB confirmed
- [ ] IAM/OIDC confirmed
- [ ] Secrets Manager confirmed
- [ ] TLS confirmed
- [ ] Monitoring confirmed
- [ ] Deployment approved

---

## Integration Execution Sequence

```text
1. Aravind DID Resolver (Enables dynamic tenant DID routing & security context)
       ↓
2. Lokesh Voice Engine (Enables live bidirectional STT ➔ LLM ➔ TTS streaming)
       ↓
3. Lokesh Exotel Carrier Integration (Plugs into Yasin's BaseTelephonyProvider for live PSTN calls)
       ↓
4. Lokesh Exotel Human Transfer (Enables live call escalation to human counselors)
       ↓
5. AWS Production Infrastructure (Provisions ECS Fargate, ALB, and Secrets — Yasin)
       ↓
6. Production CI/CD (Deploys container image via GitHub Actions OIDC — Yasin)
       ↓
7. Real End-to-End Call Testing (Exercises end-to-end phone call flow on staging)
```
