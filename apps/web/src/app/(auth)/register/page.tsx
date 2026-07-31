export default function RegisterPage() {
  return (
    <main>
      <h1>Create Account</h1>
      <form>
        <label>
          Full Name
          <input type="text" name="fullName" required />
        </label>
        <label>
          Email
          <input type="email" name="email" required />
        </label>
        <label>
          Password
          <input type="password" name="password" required minLength={8} />
        </label>
        <button type="submit">Create Account</button>
      </form>
    </main>
  );
}
