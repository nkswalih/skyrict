import { expect, test } from "@playwright/test";

import {
  acceptInvitation,
  createInvitation,
  enrollMfaViaApi,
  E2E_PASSWORD,
  getMyRoles,
  loginVerified,
  signupAccountViaBff,
  uniqueEmail,
  type Account,
  type Invitation,
} from "../helpers/backend";
import { api } from "../helpers/network";

const TOKEN_RE = /^[A-Za-z0-9_-]{40,}$/;

test.describe.serial("invitations and role assignment", () => {
  let owner: Account;
  let ownerAccess = "";
  let invite: Invitation;

  test.beforeAll(async ({ request }) => {
    owner = await signupAccountViaBff(request, "roles");
    const enrolled = await enrollMfaViaApi(request, owner);
    ownerAccess = enrolled.accessToken;
  });

  test("the owner holds tenant_owner with full permissions", async ({ request }) => {
    const mine = await getMyRoles(request, {
      accessToken: ownerAccess,
      slug: owner.slug,
    });
    expect(mine.roles).toContain("tenant_owner");
    expect(mine.permissions).toContain("*");
  });

  test("an unknown role name is rejected with a 422", async ({ request }) => {
    await expect(
      createInvitation(request, {
        accessToken: ownerAccess,
        slug: owner.slug,
        email: uniqueEmail("badrole"),
        roleName: "no-such-role",
      }),
    ).rejects.toMatchObject({
      status: 422,
      type: "https://api.skyrict.io/problems/validation-error",
    });
  });

  test("creating an invitation returns the plaintext token exactly once", async ({
    request,
  }) => {
    invite = await createInvitation(request, {
      accessToken: ownerAccess,
      slug: owner.slug,
      email: uniqueEmail("invitee"),
      roleName: "standard_user",
    });
    expect(invite.token).toMatch(TOKEN_RE);

    const list = await api<Array<Record<string, unknown>>>(
      request,
      "/invitations",
      { method: "GET", token: ownerAccess, slug: owner.slug },
    );
    const listed = list.find((item) => item.email === invite.email);
    expect(listed, "invitation appears in the tenant listing").toBeTruthy();
    expect(
      listed!["token"],
      "the listing must not expose the plaintext token",
    ).toBeUndefined();
  });

  test("an invitee can accept and inherits standard_user", async ({ request }) => {
    await acceptInvitation(request, {
      token: invite.token,
      email: invite.email,
      password: E2E_PASSWORD,
      fullName: "E2E Invitee",
      slug: owner.slug,
    });

    const invitee: Account = {
      email: invite.email,
      password: E2E_PASSWORD,
      fullName: "E2E Invitee",
      companyName: owner.companyName,
      slug: owner.slug,
      tenantId: owner.tenantId,
    };
    const enrolled = await enrollMfaViaApi(request, invitee);
    const loggedIn = await loginVerified(request, invitee, enrolled.secret);

    const mine = await getMyRoles(request, {
      accessToken: loggedIn.access_token!,
      slug: owner.slug,
    });
    expect(mine.roles).toContain("standard_user");
    expect(mine.roles).not.toContain("tenant_owner");
  });

  test("an invitation cannot be accepted twice", async ({ request }) => {
    await expect(
      acceptInvitation(request, {
        token: invite.token,
        email: invite.email,
        password: E2E_PASSWORD,
        fullName: "Sneaky Second",
        slug: owner.slug,
      }),
    ).rejects.toMatchObject({
      status: 409,
      type: "https://api.skyrict.io/problems/invitation-already-used",
    });
  });
});
