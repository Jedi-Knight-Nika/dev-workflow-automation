from dataclasses import asdict

from app.domain.workflows import WorkflowEdgeData, WorkflowGraphData, WorkflowNodeData
from app.schemas import WorkflowGraphRead


def workflow_graph_response(graph: WorkflowGraphData) -> WorkflowGraphRead:
    return WorkflowGraphRead.model_validate(
        {
            "version": graph.version,
            "nodes": [asdict(node) for node in graph.nodes],
            "edges": [asdict(edge) for edge in graph.edges],
        }
    )


def workflow_graph_data(body: WorkflowGraphRead) -> WorkflowGraphData:
    return WorkflowGraphData(
        version=body.version,
        nodes=tuple(
            WorkflowNodeData(
                id=str(node.id),
                role=node.role,
                label=node.label,
                position_x=node.position_x,
                position_y=node.position_y,
                enabled=node.enabled,
                activation_policy=node.activation_policy,
                batch_window_seconds=node.batch_window_seconds,
                integration_ids=tuple(str(item) for item in node.integration_ids),
                repository_ids=tuple(str(item) for item in node.repository_ids),
                provider=node.provider,
                model=node.model,
                system_prompt=node.system_prompt,
                model_validation_status=node.model_validation_status,
                model_validation_message=node.model_validation_message,
                model_validated_at=node.model_validated_at,
                integration_mode=node.integration_mode,
                poll_interval_seconds=node.poll_interval_seconds,
                filter_assignee_id=node.filter_assignee_id,
                filter_state_ids=tuple(node.filter_state_ids),
                integration_sync_status=node.integration_sync_status,
                integration_sync_error=node.integration_sync_error,
                integration_last_synced_at=node.integration_last_synced_at,
                reasoning_effort=node.reasoning_effort,
                max_output_tokens=node.max_output_tokens,
                temperature=node.temperature,
                timeout_minutes=node.timeout_minutes,
                max_retries=node.max_retries,
                max_review_cycles=node.max_review_cycles,
                context_depth=node.context_depth,
                rag_retrieval_depth=node.rag_retrieval_depth,
                fallback_provider=node.fallback_provider,
                fallback_model=node.fallback_model,
                agent_id=str(node.agent_id) if node.agent_id else None,
                node_type=node.node_type,
                system_node_type=node.system_node_type,
            )
            for node in body.nodes
        ),
        edges=tuple(
            WorkflowEdgeData(
                id=str(edge.id),
                source_node_id=str(edge.source_node_id),
                target_node_id=str(edge.target_node_id),
                outcome=edge.outcome,
                required=edge.required,
                job_type=edge.job_type,
                internal_task_state=edge.internal_task_state,
                external_status_key=edge.external_status_key,
                priority_override=edge.priority_override,
                configuration=edge.configuration,
            )
            for edge in body.edges
        ),
    )
