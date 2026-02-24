use core::integer::{u32, u256};
use core::ecdsa::check_ecdsa_signature;
use core::pedersen::pedersen;
use core::poseidon::poseidon_hash_span;

use openzeppelin_merkle_tree::hashes::PoseidonCHasher;
use openzeppelin_merkle_tree::merkle_proof::{process_proof, verify_poseidon};

fn hash_poseidon_single(value: felt252) -> felt252 {
    poseidon_hash_span([value].span())
}

fn hash_poseidon_pair(left: felt252, right: felt252) -> felt252 {
    poseidon_hash_span([left, right].span())
}

fn hash_poseidon_triplet(a: felt252, b: felt252, c: felt252) -> felt252 {
    poseidon_hash_span([a, b, c].span())
}

fn hash_poseidon_quad(a: felt252, b: felt252, c: felt252, d: felt252) -> felt252 {
    poseidon_hash_span([a, b, c, d].span())
}

fn assert_u256_ordering(ticket_index: felt252, deposit: u256, class_price: u256) {
    let ticket_index_u256: u256 = ticket_index.into();
    let required_deposit = (ticket_index_u256 + 1) * class_price;
    assert!(required_deposit <= deposit, "INSUFFICIENT_DEPOSIT");
}

fn assert_ticket_in_range(ticket_index: felt252, user_message_limit: u32) {
    let ticket_index_u32: u32 = ticket_index.try_into().expect('TICKET_INDEX_CONVERSION_FAILED');
    assert!(ticket_index_u32 < user_message_limit, "TICKET_INDEX_OUT_OF_RANGE");
}

fn build_rate_commitment(identity_secret: felt252, user_message_limit: u32) -> felt252 {
    let identity_commitment = hash_poseidon_single(identity_secret);
    hash_poseidon_pair(identity_commitment, user_message_limit.into())
}

/// Builds the signed refund ticket hash in canonical order:
/// (refund_commitment_prev, refund_amount, ticket_index, scope).
/// Order is part of the signature domain; changing it invalidates signatures.
fn build_refund_ticket_hash(
    refund_commitment_prev: felt252, refund_amount: felt252, ticket_index: felt252, scope: felt252,
) -> felt252 {
    hash_poseidon_quad(refund_commitment_prev, refund_amount, ticket_index, scope)
}

#[executable]
fn main(
    identity_secret: felt252,
    ticket_index: felt252,
    x: felt252,
    scope: felt252,
    user_message_limit: u32,
    deposit: u256,
    class_price: u256,
    merkle_root: felt252,
    merkle_proof: Array<felt252>,
) -> (felt252, felt252, felt252, felt252) {
    let rate_commitment = build_rate_commitment(identity_secret, user_message_limit);
    assert!(
        verify_poseidon(merkle_proof.span(), merkle_root, rate_commitment),
        "INVALID_MERKLE_PROOF",
    );

    assert_ticket_in_range(ticket_index, user_message_limit);

    let a1 = hash_poseidon_triplet(identity_secret, scope, ticket_index);
    let y = identity_secret + a1 * x;
    let nullifier = hash_poseidon_single(a1);

    assert_u256_ordering(ticket_index, deposit, class_price);

    (nullifier, x, y, merkle_root)
}

#[executable]
fn v2_kernel(
    identity_secret: felt252,
    ticket_index: felt252,
    x: felt252,
    scope: felt252,
    user_message_limit: u32,
    deposit: u256,
    class_price: u256,
    merkle_root: felt252,
    merkle_proof: Array<felt252>,
    refund_commitment_prev: felt252,
    refund_amount: felt252,
    refund_commitment_next_expected: felt252,
    remask_nonce: felt252,
    server_pubkey: felt252,
    signature_r: felt252,
    signature_s: felt252,
) -> (felt252, felt252, felt252, felt252, felt252, felt252) {
    let rate_commitment = build_rate_commitment(identity_secret, user_message_limit);
    assert!(
        verify_poseidon(merkle_proof.span(), merkle_root, rate_commitment),
        "INVALID_MERKLE_PROOF",
    );
    assert_ticket_in_range(ticket_index, user_message_limit);
    assert_u256_ordering(ticket_index, deposit, class_price);

    let a1 = hash_poseidon_triplet(identity_secret, scope, ticket_index);
    let y = identity_secret + a1 * x;
    let nullifier = hash_poseidon_single(a1);

    let refund_ticket_hash_expected = build_refund_ticket_hash(
        refund_commitment_prev, refund_amount, ticket_index, scope,
    );
    let signature_ok = check_ecdsa_signature(
        refund_ticket_hash_expected, server_pubkey, signature_r, signature_s,
    );
    assert!(signature_ok, "INVALID_REFUND_SIGNATURE");

    let refund_commitment_updated = pedersen(refund_commitment_prev, refund_amount);
    assert!(
        refund_commitment_updated == refund_commitment_next_expected, "REFUND_STATE_MISMATCH",
    );
    let refund_commitment_remasked = pedersen(refund_commitment_updated, remask_nonce);

    (
        nullifier,
        x,
        y,
        merkle_root,
        refund_commitment_updated,
        refund_commitment_remasked,
    )
}

#[executable]
fn derive_rate_commitment_root(
    identity_secret: felt252,
    user_message_limit: u32,
    merkle_proof: Array<felt252>,
) -> felt252 {
    let identity_commitment = hash_poseidon_single(identity_secret);
    let rate_commitment = hash_poseidon_pair(identity_commitment, user_message_limit.into());
    process_proof::<PoseidonCHasher>(merkle_proof.span(), rate_commitment)
}

#[executable]
fn derive_refund_transition(
    refund_commitment_prev: felt252, refund_amount: felt252, ticket_index: felt252, scope: felt252,
) -> (felt252, felt252) {
    // Helper for off-chain tooling: returns (hash-to-sign, next-state commitment).
    let refund_ticket_hash = build_refund_ticket_hash(
        refund_commitment_prev, refund_amount, ticket_index, scope,
    );
    let refund_commitment_next = pedersen(refund_commitment_prev, refund_amount);
    (refund_ticket_hash, refund_commitment_next)
}

#[cfg(test)]
mod tests {
    use super::{
        hash_poseidon_pair, hash_poseidon_single, hash_poseidon_triplet, main, v2_kernel,
    };
    use core::poseidon::poseidon_hash_span;
    use core::pedersen::pedersen;
    use openzeppelin_merkle_tree::hashes::PoseidonCHasher;
    use openzeppelin_merkle_tree::merkle_proof::process_proof;

    const IDENTITY_SECRET: felt252 = 42;
    const TICKET_INDEX: felt252 = 3;
    const USER_MESSAGE_LIMIT: u32 = 32;
    const X: felt252 = 12_345;
    const SCOPE: felt252 = 32;

    fn rate_commitment() -> felt252 {
        let identity_commitment = poseidon_hash_span([IDENTITY_SECRET].span());
        hash_poseidon_pair(identity_commitment, USER_MESSAGE_LIMIT.into())
    }

    #[test]
    fn test_main_happy_path() {
        let proof: Array<felt252> = array![];
        let root = rate_commitment();
        let (nullifier, output_x, y, output_root) = main(
            IDENTITY_SECRET,
            TICKET_INDEX,
            X,
            SCOPE,
            USER_MESSAGE_LIMIT,
            1_000.into(),
            100.into(),
            root,
            proof,
        );

        assert!(output_x == X, "X_OUTPUT_MISMATCH");
        assert!(output_root == root, "ROOT_MISMATCH");

        let a1 = hash_poseidon_triplet(IDENTITY_SECRET, SCOPE, TICKET_INDEX);
        let expected_y = IDENTITY_SECRET + a1 * X;
        let expected_nullifier = hash_poseidon_single(a1);

        assert!(nullifier == expected_nullifier, "NULLIFIER_MISMATCH");
        assert!(y == expected_y, "Y_MISMATCH");
    }

    #[test]
    fn test_main_ticket_index_zero_boundary() {
        let proof: Array<felt252> = array![];
        let root = rate_commitment();
        let (nullifier, output_x, y, output_root) = main(
            IDENTITY_SECRET,
            0,
            X,
            SCOPE,
            USER_MESSAGE_LIMIT,
            100.into(),
            100.into(),
            root,
            proof,
        );

        let a1 = hash_poseidon_triplet(IDENTITY_SECRET, SCOPE, 0);
        let expected_y = IDENTITY_SECRET + a1 * X;
        let expected_nullifier = hash_poseidon_single(a1);

        assert!(output_x == X, "X_OUTPUT_MISMATCH");
        assert!(output_root == root, "ROOT_MISMATCH");
        assert!(y == expected_y, "Y_MISMATCH");
        assert!(nullifier == expected_nullifier, "NULLIFIER_MISMATCH");
    }

    #[test]
    fn test_main_allows_boundary_deposit() {
        let proof: Array<felt252> = array![];
        let root = rate_commitment();
        let (nullifier, output_x, y, output_root) = main(
            IDENTITY_SECRET,
            TICKET_INDEX,
            X,
            SCOPE,
            USER_MESSAGE_LIMIT,
            400.into(),
            100.into(),
            root,
            proof,
        );

        let a1 = hash_poseidon_triplet(IDENTITY_SECRET, SCOPE, TICKET_INDEX);
        let expected_y = IDENTITY_SECRET + a1 * X;
        let expected_nullifier = hash_poseidon_single(a1);

        assert!(output_x == X, "X_OUTPUT_MISMATCH");
        assert!(output_root == root, "ROOT_MISMATCH");
        assert!(y == expected_y, "Y_MISMATCH");
        assert!(nullifier == expected_nullifier, "NULLIFIER_MISMATCH");
    }

    #[test]
    fn test_main_with_depth8_proof() {
        let proof: Array<felt252> = array![8073, 8090, 8107, 8124, 8141, 8158, 8175, 8192];
        let root = process_proof::<PoseidonCHasher>(proof.span(), rate_commitment());
        let (nullifier, output_x, y, output_root) = main(
            IDENTITY_SECRET,
            TICKET_INDEX,
            X,
            SCOPE,
            USER_MESSAGE_LIMIT,
            1000.into(),
            100.into(),
            root,
            proof,
        );

        assert!(output_root == root, "ROOT_MISMATCH");
        assert!(output_x == X, "X_OUTPUT_MISMATCH");
        let a1 = hash_poseidon_triplet(IDENTITY_SECRET, SCOPE, TICKET_INDEX);
        let expected_y = IDENTITY_SECRET + a1 * X;
        let expected_nullifier = hash_poseidon_single(a1);
        assert!(nullifier == expected_nullifier, "NULLIFIER_MISMATCH");
        assert!(y == expected_y, "Y_MISMATCH");
    }

    #[test]
    #[should_panic(expected: "INSUFFICIENT_DEPOSIT")]
    fn test_main_rejects_insufficient_deposit_edge() {
        let proof: Array<felt252> = array![];
        main(
            IDENTITY_SECRET,
            TICKET_INDEX,
            X,
            SCOPE,
            USER_MESSAGE_LIMIT,
            399.into(),
            100.into(),
            rate_commitment(),
            proof,
        );
    }

    #[test]
    #[should_panic(expected: "TICKET_INDEX_OUT_OF_RANGE")]
    fn test_main_rejects_ticket_index_out_of_range() {
        let proof: Array<felt252> = array![];
        main(
            IDENTITY_SECRET,
            USER_MESSAGE_LIMIT.into(),
            X,
            SCOPE,
            USER_MESSAGE_LIMIT,
            10_000.into(),
            1.into(),
            rate_commitment(),
            proof,
        );
    }

    #[test]
    #[should_panic(expected: "INVALID_MERKLE_PROOF")]
    fn test_main_rejects_wrong_root_for_depth8_proof() {
        let proof: Array<felt252> = array![8073, 8090, 8107, 8124, 8141, 8158, 8175, 8192];
        let root = process_proof::<PoseidonCHasher>(proof.span(), rate_commitment());
        main(
            IDENTITY_SECRET,
            TICKET_INDEX,
            X,
            SCOPE,
            USER_MESSAGE_LIMIT,
            1000.into(),
            100.into(),
            root + 1,
            proof,
        );
    }

    #[test]
    #[should_panic(expected: "INVALID_MERKLE_PROOF")]
    fn test_main_rejects_invalid_merkle_proof() {
        let invalid_proof = array![1, 2, 3];
        main(
            IDENTITY_SECRET,
            TICKET_INDEX,
            X,
            SCOPE,
            USER_MESSAGE_LIMIT,
            1_000.into(),
            100.into(),
            99,
            invalid_proof,
        );
    }

    #[test]
    #[should_panic(expected: "INSUFFICIENT_DEPOSIT")]
    fn test_main_rejects_insufficient_deposit() {
        let proof: Array<felt252> = array![];
        main(
            IDENTITY_SECRET,
            TICKET_INDEX,
            X,
            SCOPE,
            USER_MESSAGE_LIMIT,
            100.into(),
            50.into(),
            rate_commitment(),
            proof,
        );
    }

    #[test]
    fn test_v2_kernel_happy_path() {
        let proof: Array<felt252> = array![];
        let root = rate_commitment();
        let refund_commitment_prev = 123;
        let refund_amount = 1;
        let refund_commitment_next_expected =
            0x3639abd57ba0779f4fdd845168e3815a72834c875ee135981660ebedaa68770;
        let remask_nonce = 9;
        let server_pubkey =
            0x3fcb8c6e0c6062cac02df9ff0f3775b2263874a4cbf42643fc26713e5a8ceb6;
        let signature_r =
            0x1ef15c18599971b7beced415a40f0c7deacfd9b0d1819e03d723d8bc943cfca;
        let signature_s = 0x67075b978a9f74ca9d515e59bef04b9db63216b02f159a1bd77ec0cb88b0e6;

        let (
            nullifier,
            output_x,
            y,
            output_root,
            refund_commitment_updated,
            refund_commitment_remasked,
        ) = v2_kernel(
            IDENTITY_SECRET,
            TICKET_INDEX,
            X,
            SCOPE,
            USER_MESSAGE_LIMIT,
            1_000.into(),
            100.into(),
            root,
            proof,
            refund_commitment_prev,
            refund_amount,
            refund_commitment_next_expected,
            remask_nonce,
            server_pubkey,
            signature_r,
            signature_s,
        );

        assert!(output_x == X, "X_OUTPUT_MISMATCH");
        assert!(output_root == root, "ROOT_MISMATCH");

        let a1 = hash_poseidon_triplet(IDENTITY_SECRET, SCOPE, TICKET_INDEX);
        let expected_y = IDENTITY_SECRET + a1 * X;
        let expected_nullifier = hash_poseidon_single(a1);
        assert!(nullifier == expected_nullifier, "NULLIFIER_MISMATCH");
        assert!(y == expected_y, "Y_MISMATCH");

        let expected_updated = pedersen(refund_commitment_prev, refund_amount);
        let expected_remasked = pedersen(expected_updated, remask_nonce);
        assert!(refund_commitment_updated == expected_updated, "REFUND_COMMITMENT_MISMATCH");
        assert!(refund_commitment_remasked == expected_remasked, "REFUND_REMASK_MISMATCH");
    }

    #[test]
    #[should_panic(expected: "INVALID_REFUND_SIGNATURE")]
    fn test_v2_kernel_rejects_mismatched_bound_fields_with_same_signature() {
        let proof: Array<felt252> = array![];
        let root = rate_commitment();
        let server_pubkey =
            0x3fcb8c6e0c6062cac02df9ff0f3775b2263874a4cbf42643fc26713e5a8ceb6;
        let signature_r =
            0x1ef15c18599971b7beced415a40f0c7deacfd9b0d1819e03d723d8bc943cfca;
        let signature_s = 0x67075b978a9f74ca9d515e59bef04b9db63216b02f159a1bd77ec0cb88b0e6;

        v2_kernel(
            IDENTITY_SECRET,
            TICKET_INDEX,
            X,
            SCOPE,
            USER_MESSAGE_LIMIT,
            1_000.into(),
            100.into(),
            root,
            proof,
            123,
            2,
            0x7b99cc88f3a162c75f4a2f9a11b9c7fa10f48af0f7a7c46b2d449d5f56f8ce5,
            9,
            server_pubkey,
            signature_r,
            signature_s,
        );
    }

    #[test]
    #[should_panic(expected: "REFUND_STATE_MISMATCH")]
    fn test_v2_kernel_rejects_wrong_expected_state_transition() {
        let proof: Array<felt252> = array![];
        let root = rate_commitment();
        let server_pubkey =
            0x3fcb8c6e0c6062cac02df9ff0f3775b2263874a4cbf42643fc26713e5a8ceb6;
        let signature_r =
            0x1ef15c18599971b7beced415a40f0c7deacfd9b0d1819e03d723d8bc943cfca;
        let signature_s = 0x67075b978a9f74ca9d515e59bef04b9db63216b02f159a1bd77ec0cb88b0e6;

        v2_kernel(
            IDENTITY_SECRET,
            TICKET_INDEX,
            X,
            SCOPE,
            USER_MESSAGE_LIMIT,
            1_000.into(),
            100.into(),
            root,
            proof,
            123,
            1,
            0x3639abd57ba0779f4fdd845168e3815a72834c875ee135981660ebedaa68771,
            9,
            server_pubkey,
            signature_r,
            signature_s,
        );
    }

    #[test]
    #[should_panic(expected: "INVALID_REFUND_SIGNATURE")]
    fn test_v2_kernel_rejects_bad_signature() {
        let proof: Array<felt252> = array![];
        let root = rate_commitment();
        let server_pubkey =
            0x3fcb8c6e0c6062cac02df9ff0f3775b2263874a4cbf42643fc26713e5a8ceb6;
        let signature_r =
            0x1ef15c18599971b7beced415a40f0c7deacfd9b0d1819e03d723d8bc943cfca;
        let signature_s = 0x67075b978a9f74ca9d515e59bef04b9db63216b02f159a1bd77ec0cb88b0e6 + 1;

        v2_kernel(
            IDENTITY_SECRET,
            TICKET_INDEX,
            X,
            SCOPE,
            USER_MESSAGE_LIMIT,
            1_000.into(),
            100.into(),
            root,
            proof,
            123,
            1,
            0x3639abd57ba0779f4fdd845168e3815a72834c875ee135981660ebedaa68770,
            9,
            server_pubkey,
            signature_r,
            signature_s,
        );
    }
}
