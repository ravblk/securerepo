# SecureRepo Kubernetes Resource Requirements

## Minimum Cluster Requirements

**For Development/Testing:**
- **CPU:** 6 cores minimum
- **Memory:** 8 GiB minimum
- **Storage:** 50 GiB minimum

**For Production:**
- **CPU:** 16+ cores recommended
- **Memory:** 24+ GiB recommended
- **Storage:** 100+ GiB with backup strategy

## Per-Service Resource Requirements

### Infrastructure Services

| Service | Replicas | CPU Request | Memory Request | CPU Limit | Memory Limit | Storage |
|---------|----------|-------------|----------------|-----------|--------------|---------|
| PostgreSQL | 1 | 250m | 512Mi | 1 | 2Gi | 10Gi |
| Keycloak | 1 | 250m | 512Mi | 1 | 2Gi | 5Gi |
| Qdrant | 1 | 250m | 512Mi | 1 | 2Gi | 20Gi |
| Kafka | 1 | 250m | 512Mi | 2 | 4Gi | 10Gi |
| Langfuse | 1 | 250m | 512Mi | 500m | 1Gi | Shared with PostgreSQL |

**Infrastructure Total:** 1.25 cores / 2.5Gi (requests) | 5.5 cores / 11Gi (limits)

### Application Services

| Service | Replicas | CPU Request | Memory Request | CPU Limit | Memory Limit |
|---------|----------|-------------|----------------|-----------|--------------|
| Embedding Service | 1 | 1000m | 2Gi | 4000m | 8Gi |
| API Service | 1 | 250m | 512Mi | 1 | 1Gi |
| Frontend Service | 1 | 100m | 128Mi | 500m | 512Mi |
| Internal Rules Ingestion | 1 | 200m | 256Mi | 1 | 1Gi |
| OWASP Seeder | 1 | 100m | 256Mi | 1 | 1Gi |
| Indexer Service | 1 | 250m | 512Mi | 1 | 1Gi |
| Audit Worker | 1 | 300m | 768Mi | 2.5 | 2.5Gi |

**Applications Total:** 2.2 cores / 4.432Gi (requests) | 11 cores / 15Gi (limits)

## Total Resource Summary

### Minimum Requirements (Requests Only)
- **CPU:** 3.45 cores
- **Memory:** 6.932Gi
- **Storage:** 45Gi (PostgreSQL shared with main application and Langfuse)

### Maximum Requirements (Limits)
- **CPU:** 16.5 cores
- **Memory:** 26Gi
- **Storage:** 45Gi (PostgreSQL shared with main application and Langfuse)

### Langfuse Resource Impact
Langfuse adds minimal overhead to the infrastructure:
- **Additional CPU:** 250m (requests) | 500m (limits)
- **Additional Memory:** 512Mi (requests) | 1Gi (limits)
- **Storage:** Uses existing PostgreSQL (no additional storage required)
- **Network:** Minimal overhead for trace data transmission

## Scaling Recommendations

### Production Environment
- **API Service:** Scale to 2-3 replicas (current: 1)
- **Frontend Service:** Scale to 2-3 replicas (current: 1)
- **Audit Worker:** Scale to 2-4 replicas (current: 1)
- **Embedding Service:** Consider horizontal scaling with load balancer
- **Langfuse:** Scale to 2 replicas for HA with shared PostgreSQL

### High-Traffic Environment
- Add Horizontal Pod Autoscaler (HPA) for:
  - API Service: 2-10 replicas
  - Frontend Service: 2-5 replicas
  - Audit Worker: 2-8 replicas

## Resource Optimization Tips

1. **Memory Optimization:**
   - Reduce Java heap sizes for Kafka and Keycloak
   - Adjust PostgreSQL shared_buffers and work_mem
   - Tune Qdrant memory settings

2. **CPU Optimization:**
   - Use CPU limits effectively to prevent runaway processes
   - Enable requests for proper scheduling
   - Consider using CPU requests > limits for bursty workloads

3. **Storage Optimization:**
   - Use storage classes with appropriate I/O profiles
   - Implement backup strategies for databases
   - Monitor storage usage and set up alerts

## Monitoring Recommendations

### Key Metrics to Monitor
- Pod CPU/Memory usage vs requests/limits
- Pod restart counts
- PVC storage utilization
- Network traffic between services
- Database connection counts
- Kafka consumer lag
- Queue depth in services

### Alerting Thresholds
- CPU > 80% of limit for > 5 minutes
- Memory > 85% of limit for > 5 minutes
- Pod restart rate > 3/hour
- PVC utilization > 80%
- Response time > 1s for API
- Database connections > 80%
- Kafka consumer group lag > 1000 messages

## Ready for Production Checklist

- [ ] Resource requests and limits are properly configured
- [ ] HPA rules are defined for scalable services
- [ ] Pod Disruption Budgets are set up
- [ ] Network policies are configured
- [ ] RBAC policies are properly restricted
- [ ] Secrets are managed securely (external Secret store)
- [ ] Database backups are automated
- [ ] Monitoring and alerting are configured
- [ ] Log aggregation is set up
- [ ] TLS/SSL is enabled for external traffic
- [ ] DNS configuration is complete
- [ ] Ingress/LB controllers are configured
- [ ] Disaster recovery procedures are documented
- [ ] Rollback procedures are tested

## Troubleshooting Resource Issues

### Pods in Pending State
- Check node resources: `kubectl describe node <node-name>`
- Verify PVCs are bound: `kubectl get pvc -n securerepo`
- Review resource quotas: `kubectl describe resourcequota`

### Pods in CrashLoopBackOff
- Check logs: `kubectl logs -n securerepo <pod>`
- Verify resource limits are sufficient
- Check if required services are available

### High Memory Usage
- Review JVM heap sizes embedded in container images
- Check for memory leaks in applications
- Consider vertical scaling for memory-intensive services

### High CPU Usage
- Profile application performance
- Review database query performance
- Check if indexing operations are causing spikes
