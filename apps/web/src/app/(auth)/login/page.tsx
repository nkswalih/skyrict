export default function LoginPage() {
  return (
    <main>
      <h1>Sign In</h1>
      <form>
        <label>
          Email
          <input type="email" name="email" required />
        </label>
        <label>
          Password
          <input type="password" name="password" required />
        </label>
        <button type="submit">Sign In</button>
      </form>
    </main>
  );
}
