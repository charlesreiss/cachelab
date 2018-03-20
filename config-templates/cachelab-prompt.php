<?php
require "staff.php";
if ($isstaff) {
    $staff_0_or_1 = "1";
    if ($_GET['nostaff']) {
        $staff_0_or_1 = "0";
    }
} else {
    $staff_0_or_1 = "0";
}
$the_info = '{"username":"'.$user.'","timestamp":' . time() . ',"staff":'. $staff_0_or_1 . '}';
$key = 'XXX';
$the_hash = hash_hmac('sha512', $the_info, $key);
?>
<form action="https://archimedes.cs.virginia.edu:3331/login-setup" method="post" id="main">
    <input type="hidden" name="info" value="<?php echo htmlspecialchars($the_info) ?>">
    <input type="hidden" name="mac" value="<?php echo htmlspecialchars($the_hash) ?>">
    <input type="submit" name="continue">
</form>
<p>
About to login with staff=<?= $staff_0_or_1 ?> and user=<?= $user ?>.
</p>
<?php
if ($isstaff) {
?>
    <h2>Staff only functionality</h2>
    <p>Add <tt>?nostaff=1&amp;asuser=mst3k</tt> to login as mst3k and not staff.
    <p>Add <tt>?asuser=mst3k</tt> to login as mst3k and staff.
<?php
}
?>
