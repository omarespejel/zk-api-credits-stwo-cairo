use core::poseidon::poseidon_hash_span;
use core::integer::u256;

use openzeppelin_merkle_tree::merkle_proof::verify_poseidon;

fn hash_poseidon_single(value: felt252) -> felt252 {
    poseidon_hash_span([value].span())
}

fn hash_poseidon_pair(left: felt252, right: felt252) -> felt252 {
    poseidon_hash_span([left, right].span())
}

fn assert_u256_ordering(ticket_index: felt252, deposit: u256, class_price: u256) {
    let ticket_index_u256: u256 = ticket_index.into();
    let required_deposit = (ticket_index_u256 + 1) * class_price;
    assert!(required_deposit <= deposit, "INSUFFICIENT_DEPOSIT");
}

#[executable]
fn main(
    identity_secret: felt252,
    ticket_index: felt252,
    x: felt252,
    deposit: u256,
    class_price: u256,
    merkle_root: felt252,
    merkle_proof: Array<felt252>,
) -> (felt252, felt252, felt252, felt252) {
    let identity_commitment = hash_poseidon_single(identity_secret);
    assert!(
        verify_poseidon(merkle_proof.span(), merkle_root, identity_commitment),
        "INVALID_MERKLE_PROOF",
    );

    let a1 = hash_poseidon_pair(identity_secret, ticket_index);
    let y = identity_secret + a1 * x;
    let nullifier = hash_poseidon_single(a1);

    assert_u256_ordering(ticket_index, deposit, class_price);

    (nullifier, x, y, merkle_root)
}

#[cfg(test)]
mod tests {
    use super::{main, hash_poseidon_pair, hash_poseidon_single};
    use openzeppelin_merkle_tree::merkle_proof::process_proof;
    use openzeppelin_merkle_tree::hashes::PoseidonCHasher;
    use core::poseidon::poseidon_hash_span;

    const IDENTITY_SECRET: felt252 = 42;
    const TICKET_INDEX: felt252 = 3;
    const X: felt252 = 12_345;

    #[test]
    fn test_main_happy_path() {
        let identity_commitment = poseidon_hash_span([IDENTITY_SECRET].span());
        let proof: Array<felt252> = array![];
        let (nullifier, output_x, y, root) = main(
            IDENTITY_SECRET,
            TICKET_INDEX,
            X,
            1_000.into(),
            100.into(),
            identity_commitment,
            proof,
        );

        assert!(output_x == X, "X_OUTPUT_MISMATCH");
        assert!(root == identity_commitment, "ROOT_MISMATCH");

        let a1 = hash_poseidon_pair(IDENTITY_SECRET, TICKET_INDEX);
        let expected_y = IDENTITY_SECRET + a1 * X;
        let expected_nullifier = hash_poseidon_single(a1);

        assert!(nullifier == expected_nullifier, "NULLIFIER_MISMATCH");
        assert!(y == expected_y, "Y_MISMATCH");
    }

    #[test]
    fn test_main_ticket_index_zero_boundary() {
        let identity_commitment = poseidon_hash_span([IDENTITY_SECRET].span());
        let proof: Array<felt252> = array![];
        let (nullifier, output_x, y, root) = main(
            IDENTITY_SECRET,
            0,
            X,
            100.into(),
            100.into(),
            identity_commitment,
            proof,
        );

        let a1 = hash_poseidon_pair(IDENTITY_SECRET, 0);
        let expected_y = IDENTITY_SECRET + a1 * X;
        let expected_nullifier = hash_poseidon_single(a1);

        assert!(output_x == X, "X_OUTPUT_MISMATCH");
        assert!(root == identity_commitment, "ROOT_MISMATCH");
        assert!(y == expected_y, "Y_MISMATCH");
        assert!(nullifier == expected_nullifier, "NULLIFIER_MISMATCH");
    }

    #[test]
    fn test_main_allows_boundary_deposit() {
        let identity_commitment = poseidon_hash_span([IDENTITY_SECRET].span());
        let proof: Array<felt252> = array![];
        let (nullifier, output_x, y, root) = main(
            IDENTITY_SECRET,
            TICKET_INDEX,
            X,
            400.into(),
            100.into(),
            identity_commitment,
            proof,
        );

        let a1 = hash_poseidon_pair(IDENTITY_SECRET, TICKET_INDEX);
        let expected_y = IDENTITY_SECRET + a1 * X;
        let expected_nullifier = hash_poseidon_single(a1);

        assert!(output_x == X, "X_OUTPUT_MISMATCH");
        assert!(root == identity_commitment, "ROOT_MISMATCH");
        assert!(y == expected_y, "Y_MISMATCH");
        assert!(nullifier == expected_nullifier, "NULLIFIER_MISMATCH");
    }

    #[test]
    fn test_main_with_depth8_proof() {
        let proof: Array<felt252> = array![
            8073, 8090, 8107, 8124, 8141, 8158, 8175, 8192
        ];
        let identity_commitment = poseidon_hash_span([IDENTITY_SECRET].span());
        let merkle_root = process_proof::<PoseidonCHasher>(proof.span(), identity_commitment);
        let (nullifier, output_x, y, root) = main(
            IDENTITY_SECRET,
            TICKET_INDEX,
            X,
            1000.into(),
            100.into(),
            merkle_root,
            proof,
        );

        assert!(root == merkle_root, "ROOT_MISMATCH");
        assert!(output_x == X, "X_OUTPUT_MISMATCH");
        let a1 = hash_poseidon_pair(IDENTITY_SECRET, TICKET_INDEX);
        let expected_y = IDENTITY_SECRET + a1 * X;
        let expected_nullifier = hash_poseidon_single(a1);
        assert!(nullifier == expected_nullifier, "NULLIFIER_MISMATCH");
        assert!(y == expected_y, "Y_MISMATCH");
    }

    #[test]
    #[should_panic(expected: "INSUFFICIENT_DEPOSIT")]
    fn test_main_rejects_insufficient_deposit_edge() {
        let identity_commitment = poseidon_hash_span([IDENTITY_SECRET].span());
        let proof: Array<felt252> = array![];
        main(
            IDENTITY_SECRET,
            TICKET_INDEX,
            X,
            399.into(),
            100.into(),
            identity_commitment,
            proof,
        );
    }

    #[test]
    #[should_panic(expected: "INVALID_MERKLE_PROOF")]
    fn test_main_rejects_wrong_root_for_depth8_proof() {
        let proof: Array<felt252> = array![
            8073, 8090, 8107, 8124, 8141, 8158, 8175, 8192
        ];
        let identity_commitment = poseidon_hash_span([IDENTITY_SECRET].span());
        let merkle_root = process_proof::<PoseidonCHasher>(proof.span(), identity_commitment);
        main(
            IDENTITY_SECRET,
            TICKET_INDEX,
            X,
            1000.into(),
            100.into(),
            merkle_root + 1,
            proof,
        );
    }

    #[test]
    fn test_process_proof_depth1_matches_expected_root() {
        let proof: Array<felt252> = array![8073];
        let identity_commitment = poseidon_hash_span([IDENTITY_SECRET].span());
        let expected_root = 3226140784751492677570441901450059168905283072218262979618999391350193612117;
        let merkle_root = process_proof::<PoseidonCHasher>(proof.span(), identity_commitment);
        assert!(merkle_root == expected_root, "ROOT_MISMATCH");
    }

    #[test]
    #[should_panic(expected: "INVALID_MERKLE_PROOF")]
    fn test_main_rejects_invalid_merkle_proof() {
        let invalid_proof = array![1, 2, 3];
        main(
            IDENTITY_SECRET,
            TICKET_INDEX,
            X,
            1_000.into(),
            100.into(),
            99,
            invalid_proof,
        );
    }

    #[test]
    #[should_panic(expected: "INSUFFICIENT_DEPOSIT")]
    fn test_main_rejects_insufficient_deposit() {
        let identity_commitment = poseidon_hash_span([IDENTITY_SECRET].span());
        let proof: Array<felt252> = array![];
        main(
            IDENTITY_SECRET,
            TICKET_INDEX,
            X,
            100.into(),
            50.into(),
            identity_commitment,
            proof,
        );
    }

}
