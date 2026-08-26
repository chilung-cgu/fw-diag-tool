"""Shared transaction status classification for I2C views and reports."""

from __future__ import annotations

from enum import Enum

from fw_diag_tool.i2c.models import AckType, I2CDirection, I2CTransaction


class TransactionStatus(str, Enum):
    """Protocol/evidence status shown for one logical transaction."""

    EVIDENCE_INCOMPLETE = "EVIDENCE INCOMPLETE"
    ADDR_NAK = "ADDR NAK"
    DATA_NAK = "DATA NAK"
    READ_END_NAK = "READ END NAK"
    ACK_UNKNOWN = "ACK UNKNOWN"
    NO_STOP = "NO STOP"
    ABORTED = "ABORTED"
    ACK = "ACK"


def get_transaction_status(
    transaction: I2CTransaction,
    *,
    next_transaction: I2CTransaction | None = None,
) -> TransactionStatus:
    """Return the canonical status for a transaction.

    Status precedence keeps a transport abort and incomplete source evidence
    ahead of protocol ACK interpretation.  A known address NACK remains more
    specific than a missing STOP; a repeated-start boundary is not treated as
    a missing STOP.
    """

    if not isinstance(transaction, I2CTransaction):
        raise TypeError("transaction must be an I2CTransaction")
    if transaction.is_aborted:
        return TransactionStatus.ABORTED
    if (
        transaction.source_error
        or not transaction.address_available
        or not transaction.direction_available
        or not isinstance(transaction.direction, I2CDirection)
    ):
        return TransactionStatus.EVIDENCE_INCOMPLETE
    if transaction.address_ack == AckType.NACK:
        return TransactionStatus.ADDR_NAK
    followed_by_repeated_start = bool(
        getattr(transaction, "ended_by_repeated_start", False)
        or (next_transaction is not None and next_transaction.is_repeated_start)
    )
    if (
        not transaction.has_stop
        and not transaction.is_repeated_start
        and not followed_by_repeated_start
    ):
        return TransactionStatus.NO_STOP
    if transaction.has_unexpected_data_nack:
        return TransactionStatus.DATA_NAK
    if transaction.has_normal_read_termination_nack:
        return TransactionStatus.READ_END_NAK
    if transaction.address_ack in (AckType.NONE, None) or any(
        packet.ack in (AckType.NONE, None)
        for packet in transaction.byte_packets
        if not packet.is_address
    ):
        return TransactionStatus.ACK_UNKNOWN
    return TransactionStatus.ACK


def transaction_status(transaction: I2CTransaction) -> str:
    """Return the canonical status label as a string."""

    return get_transaction_status(transaction).value


def get_i2c_transaction_status(transaction: I2CTransaction) -> TransactionStatus:
    """Backward/semantic alias for callers naming the I2C domain explicitly."""

    return get_transaction_status(transaction)


I2CTransactionStatus = TransactionStatus
classify_transaction_status = get_transaction_status
transaction_status_label = transaction_status


__all__ = [
    "I2CTransactionStatus",
    "TransactionStatus",
    "classify_transaction_status",
    "get_i2c_transaction_status",
    "get_transaction_status",
    "transaction_status",
    "transaction_status_label",
]
