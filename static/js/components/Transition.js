const Transition = ({ children, show }) => {
    const [shouldRender, setRender] = React.useState(show);

    React.useEffect(() => {
        if (show) setRender(true);
    }, [show]);

    const onAnimationEnd = () => {
        if (!show) setRender(false);
    };

    return (
        shouldRender && (
            <div
                className={`transition ${show ? "show" : "hide"}`}
                onAnimationEnd={onAnimationEnd}
            >
                {children}
            </div>
        )
    );
}; 