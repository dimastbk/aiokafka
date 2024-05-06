import collections
import logging
from typing import Dict, List, Set

from aiokafka.cluster import ClusterMetadata
from aiokafka.coordinator.assignors.abstract import AbstractPartitionAssignor
from aiokafka.coordinator.protocol import (
    ConsumerProtocolMemberAssignment,
    ConsumerProtocolMemberMetadata,
)

log = logging.getLogger(__name__)


class RangePartitionAssignor(AbstractPartitionAssignor):
    """
    The range assignor works on a per-topic basis. For each topic, we lay out
    the available partitions in numeric order and the consumers in
    lexicographic order. We then divide the number of partitions by the total
    number of consumers to determine the number of partitions to assign to each
    consumer. If it does not evenly divide, then the first few consumers will
    have one extra partition.

    For example, suppose there are two consumers C0 and C1, two topics t0 and
    t1, and each topic has 3 partitions, resulting in partitions t0p0, t0p1,
    t0p2, t1p0, t1p1, and t1p2.

    The assignment will be:
        C0: [t0p0, t0p1, t1p0, t1p1]
        C1: [t0p2, t1p2]
    """

    name = "range"
    version = 0

    @classmethod
    def assign(
        cls,
        cluster: ClusterMetadata,
        members: Dict[str, ConsumerProtocolMemberMetadata],
    ) -> Dict[str, ConsumerProtocolMemberAssignment]:
        consumers_per_topic: Dict[str, List[str]] = collections.defaultdict(list)
        for member, metadata in members.items():
            for topic in metadata.subscription:
                consumers_per_topic[topic].append(member)

        # construct {member_id: {topic: [partition, ...]}}
        assignment: Dict[str, Dict[str, List[int]]] = collections.defaultdict(dict)

        for topic, consumers_for_topic in consumers_per_topic.items():
            partitions = cluster.partitions_for_topic(topic)
            if partitions is None:
                log.warning("No partition metadata for topic %s", topic)
                continue
            partitions_list = sorted(partitions)
            consumers_for_topic.sort()

            partitions_per_consumer = len(partitions_list) // len(consumers_for_topic)
            consumers_with_extra = len(partitions_list) % len(consumers_for_topic)

            for i, member in enumerate(consumers_for_topic):
                start = partitions_per_consumer * i
                start += min(i, consumers_with_extra)
                length = partitions_per_consumer
                if not i + 1 > consumers_with_extra:
                    length += 1
                assignment[member][topic] = partitions_list[start : start + length]

        protocol_assignment: Dict[str, ConsumerProtocolMemberAssignment] = {}
        for member_id in members:
            protocol_assignment[member_id] = ConsumerProtocolMemberAssignment(
                cls.version, sorted(assignment[member_id].items()), b""
            )
        return protocol_assignment

    @classmethod
    def metadata(cls, topics: Set[str]) -> ConsumerProtocolMemberMetadata:
        return ConsumerProtocolMemberMetadata(cls.version, list(topics), b"")

    @classmethod
    def on_assignment(cls, assignment: ConsumerProtocolMemberAssignment) -> None:
        pass
